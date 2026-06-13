from __future__ import annotations

from contextlib import contextmanager
import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.pending_invoice_read_model_service import PendingInvoiceReadModelService
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
        self.completed.append((tenant_id, scope_type, scope_key))


def _pending_invoice_expected_source_versions() -> dict[str, object]:
    return {
        "pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v1",
        "pending_invoice_tag_groups_version": 1,
        "pending_output_invoice_tag_groups_version": 1,
        "bank_auto_tag_rules_version": 1,
        "oa_attachment_invoice_parser_version": "2026-05-28-attachment-status-v1:2026-05-11-evidence-v1",
        "oa_projection_sync_version": "2026-05-28-scope-replace-v1",
        "bank_detail_source_versions": {},
    }


class SearchPendingConnection:
    def __init__(
        self,
        *,
        search_rows: list[dict] | None = None,
        pending_rows: list[dict] | None = None,
        pending_source_counts: dict[str, int] | None = None,
        pending_filter_option_rows: list[dict] | None = None,
        dirty: bool = False,
        pending_scope_exists: bool = True,
    ) -> None:
        self.search_rows = list(search_rows or [])
        self.pending_rows = list(pending_rows or [])
        self.pending_source_counts = dict(pending_source_counts or {"expense": len(self.pending_rows)})
        self.pending_filter_option_rows = list(pending_filter_option_rows or [])
        self.dirty = dirty
        self.pending_scope_exists = pending_scope_exists
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from ranked_options" in normalized:
            return self.pending_filter_option_rows
        if "from read_model.search_index_rows" in normalized:
            return self.search_rows
        if "from read_model.pending_invoice_scopes" in normalized:
            return [
                {
                    "scope_key": params[0],
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            ] if self.pending_scope_exists else []
        if "from read_model.pending_invoice_rows" in normalized and "group by direction" in normalized:
            return [
                {"direction": direction, "count": count}
                for direction, count in sorted(self.pending_source_counts.items())
            ]
        if "from read_model.pending_invoice_rows" in normalized:
            return self.pending_rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        if "count(*)" in normalized and "from read_model.pending_invoice_rows" in normalized:
            return {"count": len(self.pending_rows)}
        return None


class PendingProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-1",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "工商银行",
                    "account_no": "622200001234",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_applicant": "",
                    "oa_project_name": "",
                    "relation_case_ids": [],
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    }
                }
            }
        return None


class PendingProjectionFacadeConnection(PendingProjectionConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 5,
                        "definitions": [
                            {"code": "service_fee", "label": "服务费", "status": "active"},
                            {
                                "code": "equipment_purchase",
                                "label": "设备采购",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["设备采购"]},
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 5,
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": ["equipment_purchase"]},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    }
                }
            }
        return None


class CapturePendingInvoiceReadRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_pending_invoice_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved.append(
            {
                "scope_key": scope_key,
                "rows": list(rows),
                "source_versions": dict(source_versions or {}),
            }
        )


class FakeBankTransactionTagFacade:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def list_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_bank_tag_read",
    ) -> dict[str, object]:
        self.calls.append(
            {
                "month": month,
                "direction": direction,
                "category_codes": list(category_codes or []),
                "require_fresh": require_fresh,
                "reason": reason,
            }
        )
        return self.payload


class FakeWorkbenchRelationReadFacade:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "row_ids": list(row_ids),
                "require_fresh": require_fresh,
                "reason": reason,
                "month_hint": month_hint,
                "scope_keys_hint": list(scope_keys_hint or []),
            }
        )
        return self.payload


class PendingProjectionOaBankConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-oa-bank",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "云南溯源科技有限公司",
                    "account_no": "622200001234",
                    "bank_name": "招商银行",
                    "bank_short_name": "招行",
                    "counterparty_account_no": "622200009999",
                    "counterparty_bank_name": "招商银行昆明分行",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_summaries": [
                        {
                            "id": "oa-pay-2048",
                            "applicant": "杨丽萍",
                            "application_type": "支付申请",
                            "project_name": "大理项目",
                            "status": "已完成",
                            "form_no": "2048",
                            "detail_available": True,
                            "relation_case_id": "case-oa-bank",
                        }
                    ],
                    "oa_applicant": "杨丽萍",
                    "oa_project_name": "大理项目",
                    "relation_case_ids": ["case-oa-bank"],
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    }
                }
            }
        return None


class PendingProjectionCandidateOaConnection(PendingProjectionOaBankConnection):
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-oa-bank",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "云南溯源科技有限公司",
                    "account_no": "622200001234",
                    "bank_name": "招商银行",
                    "bank_short_name": "招行",
                    "counterparty_account_no": "622200009999",
                    "counterparty_bank_name": "招商银行昆明分行",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_summaries": [
                        {
                            "id": "candidate:wrong-oa-id",
                            "applicant": "杨丽萍",
                            "application_type": "支付申请",
                            "project_name": "大理项目",
                            "status": "已完成",
                            "form_no": "2048",
                            "detail_available": False,
                            "relation_case_id": "candidate:oa-bank",
                        }
                    ],
                    "oa_applicant": "杨丽萍",
                    "oa_project_name": "大理项目",
                    "relation_case_ids": ["candidate:oa-bank"],
                }
            ]
        return []


class PendingComplementProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-fee", "fee", "手续费"),
                self._row("txn-salary", "salary", "工资"),
                self._row("txn-custom-meal", "custom_meal", "餐饮"),
                self._row("txn-no-category", "", ""),
                self._row("txn-archived", "custom_archived", "归档"),
                self._row("txn-unknown", "unknown_external_code", "未知"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 7,
                        "definitions": [
                            {"code": "fee", "label": "手续费", "status": "active"},
                            {"code": "salary", "label": "工资", "status": "active"},
                            {
                                "code": "custom_meal",
                                "label": "餐饮",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["餐饮"]},
                            },
                            {"code": "custom_archived", "label": "归档", "status": "archived"},
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["legacy_requires_should_be_ignored"]},
                            "bank_statement_as_invoice": {"tag_codes": ["fee"]},
                            "no_invoice_required": {"tag_codes": ["salary"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": (
                {"category_code": category_code, "category_label": category_label}
                if category_code
                else {}
            ),
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "relation_case_ids": [],
        }


class PendingRuleClosureProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-fee", "fee", "手续费"),
                self._row("txn-internal-transfer", "internal_transfer", "内部转账"),
                self._row("txn-salary", "salary", "工资"),
                self._row("txn-no-category", "", ""),
                self._row("txn-unknown", "unknown_external_code", "未知"),
                self._row("txn-archived", "archived_training", "历史培训"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 11,
                        "definitions": [
                            {
                                "code": "fee",
                                "label": "手续费",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["手续费"]},
                            },
                            {
                                "code": "internal_transfer",
                                "label": "内部转账",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["内部转账"]},
                            },
                            {
                                "code": "salary",
                                "label": "工资",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["工资"]},
                            },
                            {
                                "code": "archived_training",
                                "label": "历史培训",
                                "status": "archived",
                                "rules": {"match_fields": ["all_text"], "contains": ["培训"]},
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["legacy_requires_should_be_ignored"]},
                            "bank_statement_as_invoice": {"tag_codes": ["internal_transfer"]},
                            "no_invoice_required": {"tag_codes": ["salary"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": (
                {"category_code": category_code, "category_label": category_label}
                if category_code
                else {}
            ),
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "relation_case_ids": [],
        }


class PendingEffectiveCategoryProjectionConnection:
    def __init__(self, *, direction: str = "expense") -> None:
        self.direction = direction

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            if self.direction == "income":
                return [
                    self._row("txn-income-service", "service_income", "服务收入", ["收入", "服务收入"]),
                    self._row("txn-income-cash", "cash_sale", "现金销售", ["收入", "现金销售"]),
                    self._row("txn-income-unknown", "unknown_income", "未知收入", ["收入", "未知收入"]),
                ]
            return [
                self._row("txn-equipment", "equipment_purchase", "设备采购", ["货款", "设备采购"]),
                self._row("txn-expense-unknown", "unknown_expense", "未知支出", ["货款", "未知支出"]),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 12,
                        "definitions": [
                            {"code": "equipment_purchase", "label": "设备采购", "status": "active", "direction": "expense", "rules": {"match_fields": ["all_text"], "contains": ["设备采购"]}},
                            {"code": "service_income", "label": "服务收入", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["服务收入"]}},
                            {"code": "cash_sale", "label": "现金销售", "status": "active", "direction": "income", "rules": {"match_fields": ["all_text"], "contains": ["现金销售"]}},
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "bank_statement_as_invoice": {"tag_codes": ["equipment_purchase"]},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    },
                    "pending_output_invoice_tag_groups": {
                        "groups": {
                            "no_invoice_required": {"tag_codes": []},
                            "cash_income": {"tag_codes": ["cash_sale"]},
                        }
                    },
                }
            }
        return None

    @staticmethod
    def _row(transaction_id: str, category_code: str, category_label: str, label_path: list[str]) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "转账",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": {
                "effective_category_code": category_code,
                "effective_category_label": category_label,
                "effective_category_primary_label": label_path[0] if label_path else "",
                "effective_category_sub_label": label_path[1] if len(label_path) > 1 else category_label,
                "effective_category_label_path": label_path,
            },
            "invoices": [],
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "income_status_override": None,
            "relation_case_ids": [],
        }


class PendingIncomeProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                self._row("txn-output", "service_income", "服务收入", invoices=[{"id": "out-1", "total_with_tax": "118.00"}]),
                self._row("txn-no-invoice", "internal_transfer", "内部转账"),
                self._row("txn-cash", "cash_sale", "现金销售"),
                self._row("txn-manual", "other_income", "其他收入", status_override={"status_code": "cash_income"}),
                self._row("txn-pending", "other_income", "其他收入"),
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_transaction_tags": {
                        "version": 9,
                        "definitions": [
                            {
                                "code": "service_income",
                                "label": "服务收入",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["服务"]},
                            },
                            {
                                "code": "internal_transfer",
                                "label": "内部转账",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["内部"]},
                            },
                            {
                                "code": "cash_sale",
                                "label": "现金销售",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["现金"]},
                            },
                            {
                                "code": "other_income",
                                "label": "其他收入",
                                "status": "active",
                                "rules": {"match_fields": ["all_text"], "contains": ["其他"]},
                            },
                        ],
                    },
                    "pending_output_invoice_tag_groups": {
                        "version": 3,
                        "groups": {
                            "no_invoice_required": {"tag_codes": ["internal_transfer"]},
                            "cash_income": {"tag_codes": ["cash_sale"]},
                        },
                    },
                }
            }
        return None

    @staticmethod
    def _row(
        transaction_id: str,
        category_code: str,
        category_label: str,
        *,
        invoices: list[dict] | None = None,
        status_override: dict | None = None,
    ) -> dict:
        return {
            "transaction_id": transaction_id,
            "counterparty_name_raw": transaction_id,
            "trade_time": "2026-05-20 10:00:00",
            "txn_date": "2026-05-20",
            "amount": "118.00",
            "balance": "1000.00",
            "currency": "CNY",
            "summary": "收款",
            "remark": "",
            "bank_serial_no": transaction_id,
            "account_name": "工商银行",
            "account_no": "622200001234",
            "category_payload": {
                "category_code": category_code,
                "category_label": category_label,
                "category_primary_label": "收入",
                "category_sub_label": category_label,
                "category_label_path": ["收入", category_label],
            },
            "invoices": list(invoices or []),
            "paid_total": "0.00",
            "oa_applicant": "",
            "oa_project_name": "",
            "income_status_override": dict(status_override) if status_override else None,
            "relation_case_ids": [],
        }


class SearchPendingSqlRuntimeTests(unittest.TestCase):
    def test_search_repository_reads_index_rows_without_state_fallback(self) -> None:
        connection = SearchPendingConnection(
            search_rows=[
                {
                    "source_kind": "bank",
                    "payload": {
                        "row_id": "txn-1",
                        "record_type": "bank",
                        "month": "2026-05",
                        "zone_hint": "open",
                        "matched_field": "对方户名",
                        "title": "昆明供应商",
                        "primary_meta": "2026-05-02 / 10.00 / 支出",
                        "secondary_meta": "工行 / 项目A",
                        "status_label": "未配对",
                        "jump_target": {"month": "2026-05", "row_id": "txn-1", "record_type": "bank", "zone_hint": "open"},
                    },
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.search_index(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit=20)

        self.assertEqual(payload["summary"], {"total": 1, "oa": 0, "bank": 1, "invoice": 0})
        self.assertEqual(payload["bank_results"][0]["row_id"], "txn-1")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_all_calls))

    def test_search_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._search_sql_read_repository = type("SearchRepo", (), {"search_index": lambda *_args, **_kwargs: None})()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_miss")])

    def test_search_api_reads_sql_index(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._search_sql_read_repository = type(
            "SearchRepo",
            (),
            {
                "search_index": lambda *_args, **_kwargs: {
                    "query": "昆明",
                    "filters": {"scope": "all", "month": "2026-05", "project_name": None, "status": None, "limit": 20},
                    "summary": {"total": 1, "oa": 0, "bank": 1, "invoice": 0},
                    "oa_results": [],
                    "bank_results": [{"row_id": "txn-1"}],
                    "invoice_results": [],
                    "refresh_status": "fresh",
                    "source_versions": app._search_index_expected_source_versions(),
                }
            },
        )()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search SQL hit must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_results"], [{"row_id": "txn-1"}])
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_repository_reads_rows_page_and_summary(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "invoices": [],
                        "can_create_invoice": True,
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
            pending_source_counts={"expense": 356, "income": 75},
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(direction="expense", filter="all", date_from=None, date_to=None, keyword=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["missing_invoice_rows"], 1)
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            payload["summary"]["source_summary"],
            {
                "bank_transaction_rows": 431,
                "expense_rows": 356,
                "income_rows": 75,
                "current_direction_rows": 356,
                "excluded_direction_rows": 75,
            },
        )

    def test_pending_invoice_repository_all_direction_combines_direction_summaries(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {"id": "txn-expense", "bank_transaction": {"id": "txn-expense"}, "can_create_invoice": True},
                    "missing_invoice": True,
                    "can_create_invoice": True,
                },
                {
                    "payload": {"id": "txn-income", "bank_transaction": {"id": "txn-income"}, "can_create_invoice": False},
                    "missing_invoice": True,
                    "can_create_invoice": False,
                },
            ],
            pending_source_counts={"expense": 356, "income": 75},
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(direction="all", filter="all", date_from=None, date_to=None, keyword=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 2)
        self.assertEqual(payload["summary"]["source_summary"]["current_direction_rows"], 431)
        self.assertEqual(payload["summary"]["source_summary"]["excluded_direction_rows"], 0)

    def test_pending_invoice_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

    def test_pending_invoice_repository_returns_none_when_scope_was_never_built(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False, pending_scope_exists=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsNone(payload)

    def test_pending_invoice_repository_accepts_filter_json_and_native_sort_fields(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "input_invoices": {"primary": {"seller_name": "昆明供应商"}},
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters='[{"field":"status_code","operator":"in","values":["paid_invoiced"]}]',
            sort_field="seller_name",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code", executed_sql)
        self.assertIn("seller_name asc", executed_sql)

    def test_pending_invoice_repository_filters_status_groups_by_visible_status(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-statement-paid",
                        "bank_transaction": {"id": "txn-statement-paid"},
                        "invoice_acquisition_status": {"code": "paid_invoiced"},
                        "filter_group": "bank_statement_as_invoice",
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        repository.list_pending_invoice_rows(
            direction="expense",
            filter="bank_statement_as_invoice",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code", executed_sql)
        self.assertNotIn("filter_group = %s", executed_sql)

    def test_pending_invoice_repository_supports_new_column_filter_fields_as_and_clauses(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-filtered",
                        "bank_transaction": {
                            "id": "txn-filtered",
                            "bank_short_name": "光大",
                            "account_last4": "8826",
                            "effective_tag_label_path": ["项目开销", "员工报销"],
                        },
                        "oa": {"primary": {"application_type": "支付申请"}},
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        repository.list_pending_invoice_rows(
            direction="all",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters=json.dumps(
                [
                    {"field": "bank_account", "operator": "in", "values": ["光大 8826"]},
                    {"field": "transaction_tag", "operator": "in", "values": ["项目开销 / 员工报销"]},
                    {"field": "direction", "operator": "in", "values": ["expense"]},
                    {"field": "oa_application_type", "operator": "in", "values": ["支付申请"]},
                ],
                ensure_ascii=False,
            ),
            page=1,
            page_size=50,
        )

        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("bank_short_name", executed_sql)
        self.assertIn("effective_tag_label_path", executed_sql)
        self.assertIn("direction", executed_sql)
        self.assertIn("application_type", executed_sql)
        self.assertIn(" and ", executed_sql)

    def test_pending_invoice_repository_builds_filter_options_in_sql(self) -> None:
        connection = SearchPendingConnection(
            pending_filter_option_rows=[
                {"field": "bank_account", "value": "光大 8826", "option_count": 3},
                {"field": "status_code", "value": "paid_pending_invoice", "option_count": 2},
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_filter_options(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters=json.dumps([{"field": "status_code", "operator": "in", "values": ["paid_pending_invoice"]}]),
        )

        self.assertEqual(payload["direction"], "expense")
        self.assertEqual(payload["filter"], "all")
        self.assertEqual(payload["options"]["bank_account"], [{"value": "光大 8826", "label": "光大 8826", "count": 3}])
        self.assertEqual(
            payload["options"]["status_code"],
            [{"value": "paid_pending_invoice", "label": "paid_pending_invoice", "count": 2}],
        )
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("ranked_options", executed_sql)
        self.assertIn("status_code", executed_sql)
        self.assertNotIn("limit %s offset %s", executed_sql)

    def test_pending_invoice_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"list_pending_invoice_rows": lambda *_args, **_kwargs: None},
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_miss")])

    def test_pending_invoice_api_reads_sql_page(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice SQL hit must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_api_treats_legacy_sql_payload_shape_as_refreshing(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [{"id": "txn-legacy", "bank_transaction": {"id": "txn-legacy"}, "invoices": []}],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy SQL shape must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_schema_stale")])

    def test_pending_invoice_api_source_version_stale_serves_existing_rows_and_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-stale-version",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": {
                        "pending_invoice_read_model_schema_version": "2026-05-pending-invoice-v1",
                        "pending_invoice_tag_groups_version": 999,
                    },
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("source-version stale pending invoice API must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-stale-version")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("pending_invoice_tag_groups_version_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_source_versions_stale")])

    def test_pending_invoice_api_bank_detail_source_version_stale_enqueues_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()

        class PendingRepo:
            def __init__(self) -> None:
                self.version_queries: list[dict[str, object]] = []

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-bank-tag-stale",
                            "bank_transaction": {
                                "id": "txn-bank-tag-stale",
                                "trade_time": "2026-04-23 11:18:17",
                                "effective_tag_label_path": [],
                            },
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": {
                        key: value
                        for key, value in _pending_invoice_expected_source_versions().items()
                        if key != "bank_detail_source_versions"
                    },
                }

            def pending_invoice_bank_detail_source_versions(self, **kwargs: object) -> dict[str, object]:
                self.version_queries.append(dict(kwargs))
                return {"bank_detail_schema_version": 12, "bank_auto_tag_rules_version": 7}

        pending_repo = PendingRepo()
        app._pending_invoice_sql_read_repository = pending_repo
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("bank-detail stale pending invoice API must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-bank-tag-stale")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("bank_detail_source_versions_missing", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_source_versions_stale")])
        self.assertEqual(pending_repo.version_queries[0]["direction"], "expense")
        self.assertEqual(pending_repo.version_queries[0]["filter"], "all")

    def test_pending_invoice_all_direction_miss_enqueues_expense_and_income_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"list_pending_invoice_rows": lambda *_args, **_kwargs: None},
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("all-direction pending invoice API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["all"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all", "api_miss"),
                ("pending_invoice", "income:all", "api_miss"),
            ],
        )

    def test_pending_invoice_api_serves_existing_rows_while_scope_refreshes(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-stale",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "refreshing",
                },
                "pending_invoice_source_summary": lambda *_args, **_kwargs: {
                    "bank_transaction_rows": 431,
                    "expense_rows": 356,
                    "income_rows": 75,
                    "current_direction_rows": 356,
                    "excluded_direction_rows": 75,
                },
            },
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-stale")
        self.assertEqual(payload["summary"]["source_summary"]["bank_transaction_rows"], 431)
        self.assertEqual(payload["summary"]["source_summary"]["income_rows"], 75)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_read_model_service_rejects_unconfigured_repository_without_sync_scan(self) -> None:
        service = PendingInvoiceReadModelService(
            repository=None,
            queue_repository=QueueRecorder(),
            row_normalizer=lambda rows: rows,
            settings_provider=lambda: {},
            source_versions_provider=lambda: {"pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v1"},
        )

        with self.assertRaisesRegex(Exception, "Pending invoice SQL read repository is not configured"):
            service.rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})

    def test_pending_invoice_read_model_service_all_rows_returns_refreshing_payload_without_fallback(self) -> None:
        queue = QueueRecorder()
        service = PendingInvoiceReadModelService(
            repository=type("PendingRepo", (), {"list_pending_invoice_rows": lambda *_args, **_kwargs: None})(),
            queue_repository=queue,
            row_normalizer=lambda rows: rows,
            settings_provider=lambda: {},
            source_versions_provider=lambda: {"pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v1"},
        )

        payload = service.all_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_miss")])

    def test_pending_invoice_sql_page_preserves_bank_tag_settings(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._app_settings_service = type(
            "SettingsService",
            (),
            {"get_settings_payload": lambda *_args: {"bank_transaction_tags": {"version": 7, "items": [{"code": "A1"}]}}},
        )()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": _pending_invoice_expected_source_versions(),
                }
            },
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_transaction_tags"], {"version": 7, "items": [{"code": "A1"}]})
        self.assertEqual(payload["bank_transaction_tags_version"], 7)

    def test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards(self) -> None:
        class PendingScopeConnection:
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.pending_invoice_scopes" in normalized:
                    return [
                        {
                            "scope_key": "expense:all:2026-04",
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "bank_detail_source_versions": {"bank_detail_schema_version": 12, "rules": 7},
                            },
                        },
                        {
                            "scope_key": "expense:all:2026-05",
                            "source_versions": {
                                **_pending_invoice_expected_source_versions(),
                                "bank_detail_source_versions": {"bank_detail_schema_version": 12, "rules": 8},
                            },
                        },
                    ]
                return []

            def transaction(self):
                connection = self

                class Transaction:
                    def __enter__(self) -> PendingScopeConnection:
                        return connection

                    def __exit__(self, exc_type, exc, traceback) -> bool:
                        return False

                return Transaction()

        repository = PostgresReadModelRepository(PendingScopeConnection())

        scope_row = repository._pending_invoice_scope_row("expense:all")

        self.assertIsNotNone(scope_row)
        source_versions = scope_row["source_versions"]
        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {
                "2026-04": {"bank_detail_schema_version": 12, "rules": 7},
                "2026-05": {"bank_detail_schema_version": 12, "rules": 8},
            },
        )

    def test_pending_invoice_sql_projection_emits_upgraded_four_zone_payload(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["id"], "txn-1")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_pending_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["label"], "已支付待开票")
        self.assertIn("input_invoices", payload)
        self.assertIn("oa", payload)
        self.assertEqual(payload["bank_transaction"]["account_last4"], "1234")

    def test_pending_invoice_sql_projection_consumes_workbench_relation_distribution(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["case-tian-196"],
                        "linked_oa": [
                            {
                                "id": "oa-tian-196",
                                "applicant": "田孟维",
                                "application_type": "日常报销",
                                "project_name": "云南溯源科技; 大理卷烟厂余...",
                                "detail_available": True,
                                "relation_case_id": "case-tian-196",
                            }
                        ],
                        "linked_bank_transactions": [{"id": "txn-1", "amount": "196.00"}],
                        "linked_input_invoices": [
                            {
                                "id": "oa-att-inv-70",
                                "invoice_no": "9132019MA1XM5TX71",
                                "digital_invoice_no": "",
                                "issue_date": "2026-01-20",
                                "seller_name": "中科视拓（南京）科技有限公司",
                                "seller_tax_no": "9132019MA1XM5TX71",
                                "buyer_name": "云南溯源科技有限公司",
                                "total_with_tax": "70.00",
                                "invoice_type": "input",
                                "source_kind": "oa_attachment_invoice",
                            },
                            {
                                "id": "oa-att-inv-126",
                                "invoice_no": "92532324MAC296HG5K",
                                "digital_invoice_no": "",
                                "issue_date": "2026-01-20",
                                "seller_name": "南华县沙桥镇润华清真饭店",
                                "seller_tax_no": "92532324MAC296HG5K",
                                "buyer_name": "云南溯源科技有限公司",
                                "total_with_tax": "126.00",
                                "invoice_type": "input",
                                "source_kind": "oa_attachment_invoice",
                            },
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "groups": [{"group_id": "case-tian-196", "relation_kind": "oa_bank_input_invoice"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["input_invoices"]["relation_count"], 2)
        self.assertEqual(
            [invoice["id"] for invoice in payload["input_invoices"]["summaries"]],
            ["oa-att-inv-70", "oa-att-inv-126"],
        )
        self.assertEqual(payload["input_invoices"]["payment_summary"]["invoice_total"], "196.00")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_invoiced")
        self.assertEqual(payload["oa"]["primary"]["id"], "oa-tian-196")
        self.assertEqual(payload["oa"]["relation_count"], 1)
        self.assertEqual(payload["relation_case_ids"], ["case-tian-196"])
        self.assertEqual(relation_facade.calls[0]["reason"], "pending_invoice_sql_projection")

    def test_pending_invoice_sql_projection_preserves_candidate_without_closing_status(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-1",
                        "row_type": "bank_transaction",
                        "relation_status": "candidate",
                        "group_ids": ["candidate-sql-pending"],
                        "linked_oa": [
                            {
                                "id": "oa-candidate",
                                "applicant": "候选申请人",
                                "application_type": "支付申请",
                                "project_name": "候选项目",
                                "detail_available": True,
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_bank_transactions": [
                            {
                                "id": "txn-1",
                                "amount": "118.00",
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_input_invoices": [
                            {
                                "id": "inv-candidate",
                                "invoice_no": "IN-CANDIDATE",
                                "issue_date": "2026-05-20",
                                "seller_name": "云南供应商",
                                "total_with_tax": "118.00",
                                "invoice_type": "input",
                                "relation_case_id": "candidate-sql-pending",
                                "relation_status": "candidate",
                            }
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "groups": [{"group_id": "candidate-sql-pending", "relation_status": "candidate"}],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["input_invoices"]["relation_count"], 1)
        self.assertEqual(payload["input_invoices"]["linked_relation_count"], 0)
        self.assertEqual(payload["input_invoices"]["summaries"][0]["relation_status"], "candidate")
        self.assertEqual(payload["oa"]["summaries"][0]["relation_status"], "candidate")
        self.assertEqual(payload["input_invoices"]["payment_summary"]["paid_total"], "0.00")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_pending_invoice")
        self.assertTrue(payload["can_create_invoice"])

    def test_pending_invoice_sql_projection_uses_fresh_bank_tag_facade_category(self) -> None:
        facade = FakeBankTransactionTagFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "transaction_id": "txn-1",
                        "effective_category_code": "equipment_purchase",
                        "effective_category_label": "设备采购",
                        "effective_category_primary_label": "货款",
                        "effective_category_sub_label": "设备采购",
                        "effective_category_third_label": None,
                        "effective_category_label_path": ["货款", "设备采购"],
                        "effective_category_source": "auto_confirmation",
                    }
                ],
                "source_versions": {"bank_detail": {"source_version": 9}},
                "scope_keys": ["2026-05"],
                "refresh_enqueued": False,
                "stale_reasons": [],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionFacadeConnection(),
            bank_transaction_tag_read_facade=facade,
        )

        rows = builder._pending_invoice_rows(
            direction="expense",
            filter_name="bank_statement_as_invoice",
            month="2026-05",
        )

        self.assertEqual(facade.calls[0]["require_fresh"], True)
        self.assertEqual(facade.calls[0]["direction"], "expense")
        payload = rows[0]["payload"]
        self.assertEqual(payload["filter_group"], "bank_statement_as_invoice")
        self.assertEqual(payload["bank_transaction"]["effective_tag_code"], "equipment_purchase")
        self.assertEqual(payload["bank_transaction"]["effective_tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_code"], "equipment_purchase")

    def test_pending_invoice_sql_projection_refuses_to_publish_when_bank_tags_are_not_fresh(self) -> None:
        read_repository = CapturePendingInvoiceReadRepository()
        facade = FakeBankTransactionTagFacade(
            {
                "status": "stale",
                "rows": [],
                "source_versions": {"bank_detail": {"source_version": 8}},
                "scope_keys": ["2026-05"],
                "refresh_enqueued": True,
                "stale_reasons": ["read_model_not_fresh"],
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingProjectionFacadeConnection(),
            read_model_repository=read_repository,
            bank_transaction_tag_read_facade=facade,
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            builder.rebuild_pending_invoice_read_model_scope("expense:all:2026-05")

        self.assertEqual(read_repository.saved, [])

    def test_pending_invoice_sql_projection_preserves_real_bank_and_oa_identity(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionOaBankConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["bank_transaction"]["bank_name"], "招商银行")
        self.assertEqual(payload["bank_transaction"]["account_name"], "云南溯源科技有限公司")
        self.assertEqual(payload["bank_transaction"]["counterparty_account_no"], "622200009999")
        self.assertEqual(payload["oa"]["primary"]["id"], "oa-pay-2048")
        self.assertEqual(payload["oa"]["primary"]["relation_case_id"], "case-oa-bank")
        self.assertTrue(payload["oa"]["detail_available"])
        self.assertTrue(payload["oa"]["primary"]["detail_available"])

    def test_pending_invoice_sql_projection_does_not_expose_candidate_as_oa_id(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionCandidateOaConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["relation_case_ids"], ["candidate:oa-bank"])
        self.assertIsNone(payload["oa"]["primary"])
        self.assertFalse(payload["oa"]["detail_available"])

    def test_pending_invoice_sql_projection_uses_active_complement_for_requires_invoice_filter(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingComplementProjectionConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in rows], ["txn-custom-meal"])
        self.assertEqual(rows[0]["payload"]["filter_group"], "requires_invoice")
        self.assertEqual(
            rows[0]["payload"]["invoice_acquisition_status"]["matched_rule"]["group"],
            "requires_invoice",
        )

    def test_pending_invoice_sql_projection_closes_active_rule_tag_filter_groups(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingRuleClosureProjectionConnection())

        all_rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")
        requires_rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")
        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        no_invoice_rows = builder._pending_invoice_rows(direction="expense", filter_name="no_invoice_required", month="2026-05")

        groups_by_id = {row["payload"]["id"]: row["payload"]["filter_group"] for row in all_rows}
        self.assertEqual(groups_by_id["txn-fee"], "requires_invoice")
        self.assertEqual(groups_by_id["txn-internal-transfer"], "bank_statement_as_invoice")
        self.assertEqual(groups_by_id["txn-salary"], "no_invoice_required")
        self.assertEqual(groups_by_id["txn-no-category"], "all")
        self.assertEqual(groups_by_id["txn-unknown"], "all")
        self.assertEqual(groups_by_id["txn-archived"], "all")
        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-fee"])
        self.assertEqual([row["payload"]["id"] for row in statement_rows], ["txn-internal-transfer"])
        self.assertEqual([row["payload"]["id"] for row in no_invoice_rows], ["txn-salary"])

    def test_pending_invoice_sql_projection_uses_effective_category_fields_for_expense_rules(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingEffectiveCategoryProjectionConnection())

        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        requires_rows = builder._pending_invoice_rows(direction="expense", filter_name="requires_invoice", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in statement_rows], ["txn-equipment"])
        payload = statement_rows[0]["payload"]
        self.assertEqual(payload["filter_group"], "bank_statement_as_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "bank_statement_as_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_code"], "equipment_purchase")
        self.assertEqual(payload["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(payload["bank_transaction"]["effective_tag_label_path"], ["货款", "设备采购"])
        self.assertEqual(requires_rows, [])

    def test_pending_invoice_sql_projection_excludes_already_invoiced_rows_from_statement_filter(self) -> None:
        relation_facade = FakeWorkbenchRelationReadFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-equipment",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["case-equipment-paid"],
                        "linked_oa": [],
                        "linked_bank_transactions": [{"id": "txn-equipment", "amount": "118.00", "direction": "outflow"}],
                        "linked_input_invoices": [
                            {
                                "id": "inv-equipment",
                                "invoice_no": "INV-EQUIPMENT",
                                "seller_name": "设备供应商",
                                "total_with_tax": "118.00",
                                "relation_case_id": "case-equipment-paid",
                            }
                        ],
                        "linked_output_invoices": [],
                    }
                ],
                "source_versions": {"workbench_relation_schema_version": 1},
            }
        )
        builder = SearchPendingSqlProjectionBuilder(
            connection=PendingEffectiveCategoryProjectionConnection(),
            workbench_relation_read_facade=relation_facade,
        )

        statement_rows = builder._pending_invoice_rows(direction="expense", filter_name="bank_statement_as_invoice", month="2026-05")
        all_rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        self.assertEqual(statement_rows, [])
        statuses = {row["payload"]["id"]: row["payload"]["invoice_acquisition_status"]["code"] for row in all_rows}
        self.assertEqual(statuses["txn-equipment"], "paid_invoiced")

    def test_pending_invoice_sql_projection_emits_income_output_statuses(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingIncomeProjectionConnection())

        rows = builder._pending_invoice_rows(direction="income", filter_name="all", month="2026-05")
        by_id = {row["payload"]["id"]: row["payload"] for row in rows}

        self.assertEqual(by_id["txn-output"]["invoice_acquisition_status"]["code"], "income_invoiced")
        self.assertEqual(by_id["txn-no-invoice"]["invoice_acquisition_status"]["code"], "income_no_invoice_required")
        self.assertEqual(by_id["txn-cash"]["invoice_acquisition_status"]["code"], "cash_income")
        self.assertEqual(by_id["txn-manual"]["invoice_acquisition_status"]["code"], "cash_income")
        self.assertEqual(by_id["txn-pending"]["invoice_acquisition_status"]["code"], "income_pending_invoice")
        self.assertEqual(by_id["txn-pending"]["invoice_acquisition_status"]["primary_action"], "mark_income_status")
        self.assertFalse(any(payload["can_create_invoice"] for payload in by_id.values()))
        self.assertEqual(by_id["txn-cash"]["bank_transaction"]["effective_tag_label_path"], ["收入", "现金销售"])

    def test_pending_invoice_sql_projection_filters_income_rule_groups(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingIncomeProjectionConnection())

        requires_rows = builder._pending_invoice_rows(direction="income", filter_name="requires_invoice", month="2026-05")
        no_invoice_rows = builder._pending_invoice_rows(direction="income", filter_name="no_invoice_required", month="2026-05")
        cash_rows = builder._pending_invoice_rows(direction="income", filter_name="cash_income", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-output", "txn-manual", "txn-pending"])
        self.assertEqual(requires_rows[0]["payload"]["invoice_acquisition_status"]["code"], "income_invoiced")
        self.assertEqual([row["payload"]["id"] for row in no_invoice_rows], ["txn-no-invoice"])
        self.assertEqual([row["payload"]["id"] for row in cash_rows], ["txn-cash"])

    def test_pending_invoice_sql_projection_uses_effective_category_fields_for_income_rules(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingEffectiveCategoryProjectionConnection(direction="income"))

        requires_rows = builder._pending_invoice_rows(direction="income", filter_name="requires_invoice", month="2026-05")
        cash_rows = builder._pending_invoice_rows(direction="income", filter_name="cash_income", month="2026-05")

        self.assertEqual([row["payload"]["id"] for row in requires_rows], ["txn-income-service"])
        self.assertEqual([row["payload"]["id"] for row in cash_rows], ["txn-income-cash"])
        self.assertEqual(requires_rows[0]["payload"]["invoice_acquisition_status"]["matched_rule"]["tag_label_path"], ["收入", "服务收入"])
        self.assertEqual(cash_rows[0]["payload"]["bank_transaction"]["effective_tag_code"], "cash_sale")

    def test_application_pending_invoice_invalidation_scopes_cover_income_filters(self) -> None:
        self.assertEqual(
            Application._pending_invoice_read_model_scope_keys(),
            [
                "expense:all",
                "expense:requires_invoice",
                "expense:bank_statement_as_invoice",
                "expense:no_invoice_required",
                "income:all",
                "income:requires_invoice",
                "income:no_invoice_required",
                "income:cash_income",
            ],
        )

    def test_refresh_handler_rebuilds_search_and_pending_scopes(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.search_rebuilt: list[str] = []
                self.pending_rebuilt: list[str] = []

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.search_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.pending_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        search_event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="search",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )
        pending_event = RuntimeQueueEvent(
            event_id="event-2",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        self.assertEqual(service.handle_runtime_event(search_event)["row_count"], 1)
        self.assertEqual(service.handle_runtime_event(pending_event)["row_count"], 2)

        self.assertEqual(builder.search_rebuilt, ["2026-05"])
        self.assertEqual(builder.pending_rebuilt, ["expense:all"])
        self.assertEqual(
            queue.completed,
            [("tenant-a", "search", "2026-05"), ("tenant-a", "pending_invoice", "expense:all")],
        )

    def test_refresh_handler_skips_stale_search_source_version(self) -> None:
        class FakeBuilder:
            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"stale event should not rebuild {scope_key}")

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
        service = SearchPendingReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-stale",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="search",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 3},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(queue.current_checks, [("tenant-a", "search", "2026-05", 3)])
        self.assertEqual(
            result,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 3,
            },
        )

    def test_refresh_handler_rejects_application_fallback_dependency(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            SearchPendingReadModelRefreshService(application=object(), queue_repository=QueueRecorder())

    def test_refresh_handler_expands_search_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_search_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["2026-05", "2026-04"]

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="search",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:all"])
        self.assertEqual(
            queue.refreshes,
            [("search", "2026-05", "search_all_shard"), ("search", "2026-04", "search_all_shard")],
        )
        self.assertEqual(queue.completed, [("tenant-a", "search", "all")])

    def test_refresh_handler_expands_legacy_pending_scope_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["expense:all:2026-05", "expense:all:2026-04"]

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-all",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "expense:all", "enqueued_scope_keys": ["expense:all:2026-05", "expense:all:2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:expense:all"])
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all:2026-05", "pending_invoice_month_shard"),
                ("pending_invoice", "expense:all:2026-04", "pending_invoice_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:all")])

    def test_refresh_handler_expands_pending_filter_scope_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(f"list:{scope_key}")
                return ["expense:requires_invoice:2026-05", "expense:requires_invoice:2026-04"]

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(f"rebuild:{scope_key}")
                return {"scope_key": scope_key, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-requires",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:requires_invoice",
            scope_type="pending_invoice",
            scope_key="expense:requires_invoice",
            dedupe_key=None,
            payload={"scope_key": "expense:requires_invoice"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            result,
            {
                "scope_key": "expense:requires_invoice",
                "enqueued_scope_keys": ["expense:requires_invoice:2026-05", "expense:requires_invoice:2026-04"],
                "row_count": 0,
            },
        )
        self.assertEqual(builder.calls, ["list:expense:requires_invoice"])
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:requires_invoice:2026-05", "pending_invoice_month_shard"),
                ("pending_invoice", "expense:requires_invoice:2026-04", "pending_invoice_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:requires_invoice")])

    def test_refresh_handler_rebuilds_pending_filter_month_shard(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(scope_key)

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-requires-month",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:requires_invoice:2026-05",
            scope_type="pending_invoice",
            scope_key="expense:requires_invoice:2026-05",
            dedupe_key=None,
            payload={"scope_key": "expense:requires_invoice:2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "expense:requires_invoice:2026-05", "row_count": 1})
        self.assertEqual(builder.calls, ["expense:requires_invoice:2026-05"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:requires_invoice:2026-05")])


if __name__ == "__main__":
    unittest.main()
