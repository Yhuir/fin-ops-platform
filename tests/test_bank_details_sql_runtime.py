from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.bank_detail_read_model_refresh import BankDetailReadModelRefreshService
from fin_ops_platform.services.bank_detail_read_model_repository import BankDetailReadModelRepositoryPort
from fin_ops_platform.services.bank_detail_sql_projection import BankDetailSqlProjectionBuilder
from fin_ops_platform.services.bank_details_application_service import BankDetailsApplicationService
from fin_ops_platform.services.bank_transaction_effective_category_provider import BankTransactionEffectiveCategoryProvider
from fin_ops_platform.services.bank_transaction_tag_read_facade import BankTransactionTagReadFacade
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
    _bank_detail_scope_statistics,
    _bank_detail_statistics_from_rows,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class FakeConnection:
    def __init__(
        self,
        rows: list[object] | None = None,
        app_settings_payload: dict[str, object] | None = None,
        dirty_scope_rows: list[dict[str, object]] | None = None,
        category_rows: list[dict[str, object]] | None = None,
        category_source_signature_rows: list[dict[str, object]] | None = None,
        confirmation_rows: list[dict[str, object]] | None = None,
        relation_rows: list[dict[str, object]] | None = None,
        relation_source_summary_rows: list[dict[str, object]] | None = None,
        bank_source_summary_rows: list[dict[str, object]] | None = None,
        relation_source_row: dict[str, object] | None = None,
    ) -> None:
        self.rows = list(rows or [])
        self.app_settings_payload = app_settings_payload
        self.dirty_scope_rows = list(dirty_scope_rows or [])
        self.category_rows = list(category_rows or [])
        self.category_source_signature_rows = list(category_source_signature_rows or [])
        self.confirmation_rows = list(confirmation_rows or [])
        self.relation_rows = list(relation_rows or [])
        self.relation_source_summary_rows = list(relation_source_summary_rows or [])
        self.bank_source_summary_rows = bank_source_summary_rows
        self.relation_source_row = relation_source_row
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        if "from app.app_settings" in " ".join(sql.lower().split()):
            if self.app_settings_payload is not None:
                return {"settings_payload": self.app_settings_payload}
            if self.rows and isinstance(self.rows[0], dict) and "settings_payload" in self.rows[0]:
                value = self.rows.pop(0)
                return value if isinstance(value, dict) else None
            return None
        if "from app.workbench_pair_relations" in " ".join(sql.lower().split()):
            return self.relation_source_row
        value = self.rows.pop(0) if self.rows else None
        return value if isinstance(value, dict) else None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append(("fetch_all", sql, params))
        normalized_sql = " ".join(sql.lower().split())
        if "from job.read_model_dirty_scopes" in normalized_sql:
            return list(self.dirty_scope_rows)
        if "/* bank_detail_category_source_signatures */" in normalized_sql:
            return list(self.category_source_signature_rows)
        if "/* bank_detail_relation_source_summaries */" in normalized_sql:
            return list(self.relation_source_summary_rows)
        if "/* bank_detail_canonical_source_summaries */" in normalized_sql:
            if self.bank_source_summary_rows is not None:
                return list(self.bank_source_summary_rows)
            return [
                {
                    "scope_key": scope_key,
                    "row_count": 0,
                    "context_row_count": 0,
                    "bank_transactions_updated_at": "",
                }
                for scope_key in list(params[0] if params else [])
            ]
        if "from app.bank_transaction_categories" in normalized_sql:
            return list(self.category_rows)
        if "from app.bank_transaction_category_confirmations" in normalized_sql:
            return list(self.confirmation_rows)
        if "from app.workbench_pair_relations" in normalized_sql:
            return list(self.relation_rows)
        value = self.rows.pop(0) if self.rows else []
        return list(value) if isinstance(value, list) else []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.calls.append(("execute", sql, params))
        return 0

    def execute_many(self, sql: str, params_seq: list[tuple[object, ...]]) -> int:
        self.calls.append(("execute_many", sql, tuple(params_seq)))
        return len(params_seq)

    def transaction(self):
        connection = self

        class Transaction:
            def __enter__(self) -> FakeConnection:
                return connection

            def __exit__(self, exc_type, exc, traceback) -> bool:
                return False

        return Transaction()


class _UnderlyingBankDetailReadModelRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def bank_detail_scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
        self.calls.append(("bank_detail_scope_keys_for_range", {"date_from": date_from, "date_to": date_to}))
        return ["2026-05"]

    def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
        self.calls.append(("bank_detail_scope_summary", {"scope_keys": list(scope_keys)}))
        return {"read_model_status": "fresh", "read_model_scope_keys": list(scope_keys)}

    def bank_detail_category_source_signatures(self, *, scope_keys: list[str]) -> dict[str, str]:
        self.calls.append(("bank_detail_category_source_signatures", {"scope_keys": list(scope_keys)}))
        return {scope_key: f"signature:{scope_key}" for scope_key in scope_keys}

    def list_bank_detail_transactions(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_bank_detail_transactions", dict(kwargs)))
        return {"rows": [{"id": "txn-1"}], "read_model_status": "fresh"}

    def list_bank_detail_accounts(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_bank_detail_accounts", dict(kwargs)))
        return {"accounts": [{"account_key": "icbc:6386"}], "read_model_status": "fresh"}

    def get_bank_detail_tagged_rows_by_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_bank_detail_tagged_rows_by_transaction_ids",
                {"transaction_ids": list(transaction_ids), "tenant_id": tenant_id},
            )
        )
        return {"rows": [{"transaction_id": "txn-1"}], "read_model_status": "fresh"}

    def get_bank_detail_tagged_snapshot(
        self,
        month: str,
        *,
        include_transaction_ids: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "get_bank_detail_tagged_snapshot",
                {
                    "month": month,
                    "include_transaction_ids": list(include_transaction_ids or []),
                    "tenant_id": tenant_id,
                },
            )
        )
        return {"rows": [{"transaction_id": "txn-1"}], "read_model_status": "fresh"}

    def list_bank_detail_tagged_rows_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        self.calls.append(
            (
                "list_bank_detail_tagged_rows_by_month",
                {
                    "month": month,
                    "direction": direction,
                    "category_codes": list(category_codes or []),
                    "tenant_id": tenant_id,
                },
            )
        )
        return {"rows": [{"transaction_id": "txn-1"}], "read_model_status": "fresh"}

    def list_bank_account_balances(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_bank_account_balances", dict(kwargs)))
        return {"accounts": [{"account_key": "icbc:6386"}], "balance_read_model_status": "fresh"}

    def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("bank_detail port must not expose pending invoice repository methods")


class CaptureBankDetailReadModelRepository:
    def __init__(self) -> None:
        self.saved_rows: list[dict[str, object]] = []
        self.marked_scopes: list[dict[str, object]] = []

    def save_bank_detail_rows(self, *, scope_key: str, rows: list[dict[str, object]], tenant_id: str = "default") -> None:
        self.saved_rows = list(rows)

    def mark_bank_detail_scope(self, **kwargs: object) -> None:
        self.marked_scopes.append(dict(kwargs))


class CaptureRuntimeQueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> RuntimeQueueEvent:
        self.enqueued.append(dict(kwargs))
        scope_type = str(kwargs.get("scope_type") or "")
        scope_key = str(kwargs.get("scope_key") or "")
        return RuntimeQueueEvent(
            event_id=f"event-{len(self.enqueued)}",
            tenant_id=str(kwargs.get("tenant_id") or "default"),
            event_type=f"{scope_type}.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id=scope_key,
            scope_type=scope_type,
            scope_key=scope_key,
            dedupe_key=f"{scope_type}.read_model.refresh:{scope_type}:{scope_key}",
            payload={"scope_type": scope_type, "scope_key": scope_key},
            attempts=0,
            status="pending",
            source_version=len(self.enqueued),
        )


def scope_row(scope_key: str, **overrides: object) -> dict[str, object]:
    row_count = int(overrides.get("row_count") or 0)
    default_source_versions = {
        "source_version": 3,
        "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
        "bank_transactions_context_row_count": row_count,
        "bank_transactions_updated_at": "",
        "workbench_relation_source_versions": {
            "source": "workbench_pair_relations",
            "scope_key": scope_key,
            "relation_count": 0,
            "relation_updated_at": "",
        },
    }
    row: dict[str, object] = {
        "scope_key": scope_key,
        "scope_type": "bank_detail",
        "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
        "status": "fresh",
        "row_count": 0,
        "source_version": 3,
        "source_versions": default_source_versions,
        "generated_at": "2026-05-25T00:00:00+00:00",
        "last_error": None,
    }
    override_source_versions = overrides.get("source_versions")
    row.update(overrides)
    if isinstance(override_source_versions, dict):
        row["source_versions"] = {
            **default_source_versions,
            **override_source_versions,
        }
    return row


def runtime_event(scope_key: str, *, metadata: dict[str, object] | None = None) -> RuntimeQueueEvent:
    payload: dict[str, object] = {"scope_type": "bank_detail", "scope_key": scope_key, "source_version": 7}
    if metadata is not None:
        payload["metadata"] = dict(metadata)
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type="bank_detail.read_model.refresh",
        aggregate_type="read_model",
        aggregate_id=scope_key,
        scope_type="bank_detail",
        scope_key=scope_key,
        dedupe_key=f"bank_detail.read_model.refresh:bank_detail:{scope_key}",
        payload=payload,
        attempts=0,
        status="processing",
        source_version=7,
    )


def bank_detail_projected_row(
    transaction_id: str = "txn-001",
    *,
    scope_key: str = "2026-05",
    direction: str = "expense",
    category_code: str | None = "equipment_purchase",
) -> dict[str, object]:
    return {
        "payload": {
            "id": transaction_id,
            "transaction_id": transaction_id,
            "trade_time": "2026-05-03T10:00:00+08:00",
            "trade_date": "2026-05-03",
            "direction": direction,
            "direction_label": "支" if direction == "expense" else "收",
            "amount": "23053.31",
            "signed_amount": "-23053.31" if direction == "expense" else "23053.31",
            "counterparty_name": "云南辰飞机电工程有限公司",
            "summary": "货款",
            "purpose": "设备采购",
            "bank_name": "光大银行",
            "account_last4": "8826",
            "effective_category_code": category_code,
            "effective_category_label": "设备采购" if category_code else None,
            "effective_category_primary_label": "货款" if category_code else None,
            "effective_category_sub_label": "设备采购" if category_code else None,
            "effective_category_third_label": None,
            "effective_category_label_path": ["货款", "设备采购"] if category_code else [],
            "effective_category_source": "auto_confirmation" if category_code else None,
            "effective_turnover_role": "expense",
            "effective_turnover_action_type": "purchase",
            "effective_turnover_family": "operating",
            "category_version": 7,
            "manual_category_version": 7,
            "version": 11,
        },
        "raw_payload": {"normalized_payload": {}},
        "summary": "货款",
        "purpose": "设备采购",
        "scope_key": scope_key,
    }


class FakeBankTaggedReadRepository:
    def __init__(
        self,
        *,
        by_ids_payload: dict[str, object] | None = None,
        by_month_payload: dict[str, object] | None = None,
        snapshot_payload: dict[str, object] | None = None,
        scope_summary_payload: dict[str, object] | None = None,
    ) -> None:
        self.by_ids_payload = by_ids_payload
        self.by_month_payload = by_month_payload
        self.snapshot_payload = snapshot_payload
        self.scope_summary_payload = scope_summary_payload
        self.id_calls: list[list[str]] = []
        self.month_calls: list[dict[str, object]] = []
        self.snapshot_calls: list[dict[str, object]] = []
        self.scope_summary_calls: list[dict[str, object]] = []

    def get_bank_detail_tagged_rows_by_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.id_calls.append(list(transaction_ids))
        return self.by_ids_payload

    def list_bank_detail_tagged_rows_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.month_calls.append(
            {
                "month": month,
                "direction": direction,
                "category_codes": list(category_codes or []),
                "tenant_id": tenant_id,
            }
        )
        return self.by_month_payload

    def get_bank_detail_tagged_snapshot(
        self,
        month: str,
        *,
        include_transaction_ids: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.snapshot_calls.append(
            {
                "month": month,
                "include_transaction_ids": list(include_transaction_ids or []),
                "tenant_id": tenant_id,
            }
        )
        return self.snapshot_payload

    def bank_detail_scope_summary(
        self,
        *,
        scope_keys: list[str],
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.scope_summary_calls.append({"scope_keys": list(scope_keys), "tenant_id": tenant_id})
        return self.scope_summary_payload


class FakeCategoryService:
    def __init__(self, categories: dict[str, dict[str, object]] | None = None) -> None:
        self.categories = categories or {}

    def get(self, transaction_id: str) -> dict[str, object]:
        return dict(self.categories.get(transaction_id) or {})

    def bulk_get(self, transaction_ids: list[str]) -> dict[str, dict[str, object]]:
        return {transaction_id: dict(self.categories.get(transaction_id) or {}) for transaction_id in transaction_ids}


class FakeAutoCategoryService:
    def __init__(self, suggestions: dict[str, dict[str, object]] | None = None) -> None:
        self.suggestions = suggestions or {}

    def suggestions_by_transaction_id(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        return {
            str(row.get("id") or row.get("transaction_id") or ""): dict(
                self.suggestions.get(str(row.get("id") or row.get("transaction_id") or "")) or {}
            )
            for row in rows
        }


class BankTransactionEffectiveCategoryProviderTests(unittest.TestCase):
    def test_provider_docstring_states_legacy_on_demand_boundary(self) -> None:
        doc = BankTransactionEffectiveCategoryProvider.__doc__ or ""

        self.assertIn("legacy/local", doc)
        self.assertIn("not the PostgreSQL production downstream read gateway", doc)

    def test_provider_keeps_legacy_on_demand_effective_category_resolution(self) -> None:
        provider = BankTransactionEffectiveCategoryProvider(
            category_service=FakeCategoryService(
                {
                    "txn-confirmed": {
                        "category_code": "equipment_purchase",
                        "category_label": "设备采购",
                        "category_path": ["货款", "设备采购"],
                        "category_label_path": ["货款", "设备采购"],
                        "category_primary_label": "货款",
                        "category_sub_label": "设备采购",
                        "source": "auto_confirmation",
                        "category_version": 7,
                    },
                    "txn-turnover": {
                        "category_code": "borrow_in_personal_pending_repayment",
                        "category_label": "个人暂借款：待还款",
                        "category_path": ["借入", "个人往来款", "待还款"],
                        "category_label_path": ["借入", "个人往来款", "待还款"],
                        "category_primary_label": "借入",
                        "category_sub_label": "个人往来款",
                        "category_third_label": "个人往来",
                        "turnover_role": "external",
                        "turnover_action_type": "borrow_in_principal",
                        "turnover_family": "personal",
                        "source": "turnover_ledger",
                    },
                }
            ),
            auto_category_service=FakeAutoCategoryService(
                {
                    "txn-auto": {
                        "category_code": "equipment_purchase",
                        "category_label": "设备采购",
                        "category_path": ["货款", "设备采购"],
                        "category_label_path": ["货款", "设备采购"],
                        "category_primary_label": "货款",
                        "category_sub_label": "设备采购",
                    }
                }
            ),
        )

        categories = provider.bulk_get_for_rows(
            [
                {"id": "txn-auto", "txn_direction": "outflow", "amount": "100.00"},
                {"id": "txn-confirmed", "txn_direction": "outflow", "amount": "200.00"},
                {"id": "txn-turnover", "txn_direction": "inflow", "amount": "300.00"},
                {"id": "txn-empty", "txn_direction": "outflow", "amount": "1.00"},
            ]
        )

        self.assertEqual(categories["txn-auto"]["category_code"], "equipment_purchase")
        self.assertEqual(categories["txn-auto"]["source"], "auto")
        self.assertEqual(categories["txn-confirmed"]["category_code"], "equipment_purchase")
        self.assertEqual(categories["txn-confirmed"]["source"], "manual_confirmation")
        self.assertEqual(categories["txn-confirmed"]["category_version"], 7)
        self.assertEqual(categories["txn-turnover"]["category_code"], "borrow_in_personal_pending_repayment")
        self.assertEqual(categories["txn-turnover"]["effective_category_third_label"], "个人往来")
        self.assertEqual(categories["txn-turnover"]["turnover_action_type"], "borrow_in_principal")
        self.assertIsNone(categories["txn-empty"]["category_code"])

    def test_provider_does_not_expose_read_model_freshness_contract(self) -> None:
        provider = BankTransactionEffectiveCategoryProvider(
            category_service=FakeCategoryService(),
            auto_category_service=FakeAutoCategoryService(),
        )

        self.assertFalse(hasattr(provider, "last_source_versions"))
        self.assertFalse(hasattr(provider, "get_by_transaction_ids"))
        self.assertFalse(hasattr(provider, "list_by_month"))


class BankTransactionTagReadFacadeTests(unittest.TestCase):
    def test_snapshot_for_month_returns_target_month_rows_and_cross_month_relation_rows_in_one_read(self) -> None:
        repository = FakeBankTaggedReadRepository(
            snapshot_payload={
                "read_model_status": "fresh",
                "rows": [
                    bank_detail_projected_row("txn-month", scope_key="2026-05")["payload"],
                    bank_detail_projected_row("txn-cross-month", scope_key="2026-04")["payload"],
                ],
                "target_scope_transaction_ids": ["txn-month"],
                "missing_transaction_ids": [],
                "source_versions": {
                    "2026-04": {"source_version": 2},
                    "2026-05": {"source_version": 3},
                },
                "read_model_scope_keys": ["2026-05", "2026-04"],
                "read_model_scope_signatures": {
                    "2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION},
                    "2026-04": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION},
                },
            }
        )
        facade = BankTransactionTagReadFacade(read_model_repository=repository)

        payload = facade.snapshot_for_month(
            "2026-05",
            include_transaction_ids=["txn-cross-month"],
            require_fresh=False,
        )

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(
            [row["transaction_id"] for row in payload["rows"]],
            ["txn-month", "txn-cross-month"],
        )
        self.assertEqual(
            [row["transaction_id"] for row in payload["month_rows"]],
            ["txn-month"],
        )
        self.assertEqual(
            repository.snapshot_calls,
            [
                {
                    "month": "2026-05",
                    "include_transaction_ids": ["txn-cross-month"],
                    "tenant_id": "default",
                }
            ],
        )
        self.assertEqual(repository.id_calls, [])
        self.assertEqual(repository.month_calls, [])

    def test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "fresh",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 9},
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {"2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}},
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(["txn-001"])

        self.assertEqual(payload["status"], "fresh")
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(payload["source_versions"], {"bank_detail": 9})
        self.assertEqual(payload["scope_keys"], ["2026-05"])
        self.assertEqual(queue.enqueued, [])
        row = payload["rows"][0]
        self.assertEqual(row["transaction_id"], "txn-001")
        self.assertEqual(row["direction"], "expense")
        self.assertEqual(row["effective_category_code"], "equipment_purchase")
        self.assertEqual(row["effective_category_label_path"], ["货款", "设备采购"])
        self.assertEqual(row["effective_turnover_action_type"], "purchase")
        self.assertEqual(row["category_version"], 7)
        self.assertEqual(row["manual_category_version"], 7)
        self.assertEqual(row["version"], 11)

    def test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions(self) -> None:
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "fresh",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 9},
                "read_model_scope_keys": ["2026-05"],
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(read_model_repository=repository)

        categories = facade.bulk_get_for_rows(
            [{"id": "txn-001", "txn_date": "2026-05-03", "txn_direction": "outflow", "amount": "23053.31"}]
        )

        self.assertEqual(categories["txn-001"]["category_version"], 7)
        self.assertEqual(categories["txn-001"]["manual_category_version"], 7)
        self.assertEqual(categories["txn-001"]["version"], 11)
        self.assertEqual(categories["txn-001"]["turnover_action_type"], "purchase")

    def test_source_versions_for_scope_keys_uses_scope_summary_without_loading_rows(self) -> None:
        repository = FakeBankTaggedReadRepository(
            scope_summary_payload={
                "read_model_status": "fresh",
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {
                    "2026-05": {
                        "source_versions": {
                            "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                            "row_count": 9,
                            "bank_detail_source_signature": "sig-v1",
                        }
                    }
                },
            }
        )
        facade = BankTransactionTagReadFacade(read_model_repository=repository)

        payload = facade.source_versions_for_scope_keys(["2026-05"])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(
            payload["source_versions"],
            {
                "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                "row_count": 9,
                "bank_detail_source_signature": "sig-v1",
            },
        )
        self.assertEqual(facade.last_source_versions, payload["source_versions"])
        self.assertEqual(repository.scope_summary_calls, [{"scope_keys": ["2026-05"], "tenant_id": "default"}])
        self.assertEqual(repository.id_calls, [])
        self.assertEqual(repository.month_calls, [])

    def test_source_versions_for_scope_keys_supports_bank_detail_port_without_tenant_arg(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
                self.calls.append({"scope_keys": list(scope_keys)})
                return {
                    "read_model_status": "fresh",
                    "read_model_scope_keys": list(scope_keys),
                    "read_model_scope_signatures": {
                        "2026-07": {
                            "source_versions": {
                                "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                                "row_count": 4,
                            }
                        }
                    },
                }

        repository = Repository()
        facade = BankTransactionTagReadFacade(
            read_model_repository=BankDetailReadModelRepositoryPort(repository),
        )

        payload = facade.source_versions_for_scope_keys(["2026-07"])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(
            payload["source_versions"],
            {
                "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                "row_count": 4,
            },
        )
        self.assertEqual(repository.calls, [{"scope_keys": ["2026-07"]}])

    def test_get_by_transaction_ids_requires_fresh_before_returning_publishable_rows(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "stale",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 8},
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {"2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION - 1}},
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(["txn-001"], require_fresh=True, reason="unit_test")

        self.assertEqual(payload["status"], "stale")
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["scope_keys"], ["2026-05"])
        self.assertEqual(queue.enqueued[0]["scope_type"], "bank_detail")
        self.assertEqual(queue.enqueued[0]["scope_key"], "2026-05")
        self.assertEqual(queue.enqueued[0]["reason"], "unit_test")
        self.assertIn("read_model_not_fresh", payload["stale_reasons"])

    def test_get_by_transaction_ids_refreshes_only_scope_with_effective_source_drift(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "stale",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01", "2026-02", "2026-03"],
                "read_model_scope_signatures": {
                    "2026-01": {"freshness_status": "fresh"},
                    "2026-02": {"freshness_status": "stale"},
                    "2026-03": {"freshness_status": "fresh"},
                },
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(
            ["txn-jan", "txn-feb", "txn-mar"],
            require_fresh=True,
            scope_keys_hint=["2026-01", "2026-02", "2026-03"],
        )

        self.assertEqual(payload["status"], "stale")
        self.assertEqual(
            [item["scope_key"] for item in queue.enqueued],
            ["2026-02"],
        )

    def test_get_by_transaction_ids_refreshes_only_missing_scope(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "missing",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01", "2026-02", "2026-03"],
                "read_model_scope_signatures": {
                    "2026-01": {"freshness_status": "fresh"},
                    "2026-02": {"freshness_status": "missing"},
                    "2026-03": {"freshness_status": "fresh"},
                },
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(
            ["txn-jan", "txn-feb", "txn-mar"],
            require_fresh=True,
            scope_keys_hint=["2026-01", "2026-02", "2026-03"],
        )

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(
            [item["scope_key"] for item in queue.enqueued],
            ["2026-02"],
        )

    def test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "refreshing",
                "rows": [
                    bank_detail_projected_row("txn-jan", scope_key="2026-01")["payload"],
                    bank_detail_projected_row("txn-feb", scope_key="2026-02")["payload"],
                ],
                "source_versions": {"bank_detail": 9},
                "read_model_scope_keys": ["2026-01", "2026-02"],
                "read_model_scope_signatures": {
                    "2026-01": {
                        "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                        "status": "fresh",
                        "dirty_status": "",
                    },
                    "2026-02": {
                        "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                        "status": "fresh",
                        "dirty_status": "pending",
                    },
                },
                "dirty_scopes": [{"scope_key": "2026-02", "status": "pending", "source_version": 10}],
                "missing_transaction_ids": [],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(["txn-jan", "txn-feb"], require_fresh=True)

        self.assertEqual(payload["status"], "refreshing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["scope_keys"], ["2026-01", "2026-02"])
        self.assertEqual([item["scope_key"] for item in queue.enqueued], ["2026-02"])

    def test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "fresh",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 9},
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {"2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}},
                "missing_transaction_ids": ["txn-missing"],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(["txn-001", "txn-missing"], require_fresh=True)

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual([row["transaction_id"] for row in payload["rows"]], ["txn-001"])
        self.assertEqual(payload["missing_transaction_ids"], ["txn-missing"])
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(payload["stale_reasons"], [])
        self.assertEqual(queue.enqueued, [])

    def test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "fresh",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 9},
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {"2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}},
                "missing_transaction_ids": ["txn-missing"],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        categories = facade.category_records_by_transaction_ids(["txn-001", "txn-missing"], require_fresh=True)

        self.assertEqual(sorted(categories), ["txn-001"])
        self.assertEqual(categories["txn-001"]["category_code"], "equipment_purchase")
        self.assertEqual(queue.enqueued, [])

    def test_get_by_transaction_ids_enqueues_hint_scope_when_all_projected_rows_are_missing(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "missing",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "read_model_scope_signatures": {},
                "missing_transaction_ids": ["txn-missing"],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(
            ["txn-missing"],
            require_fresh=True,
            reason="unit_test_missing",
            month_hint="2026-05",
        )

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["scope_keys"], ["2026-05"])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(queue.enqueued[0]["scope_key"], "2026-05")

    def test_get_by_transaction_ids_enqueues_all_scope_when_missing_without_hint(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_ids_payload={
                "read_model_status": "missing",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "read_model_scope_signatures": {},
                "missing_transaction_ids": ["txn-missing"],
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.get_by_transaction_ids(["txn-missing"], require_fresh=True)

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["scope_keys"], ["all"])
        self.assertEqual(queue.enqueued[0]["scope_key"], "all")

    def test_list_by_month_allows_diagnostic_stale_rows_when_fresh_not_required(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        repository = FakeBankTaggedReadRepository(
            by_month_payload={
                "read_model_status": "refreshing",
                "rows": [bank_detail_projected_row("txn-001")["payload"]],
                "source_versions": {"bank_detail": 8},
                "read_model_scope_keys": ["2026-05"],
                "read_model_scope_signatures": {"2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}},
            }
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        payload = facade.list_by_month("2026-05", direction="expense", require_fresh=False)

        self.assertEqual(payload["status"], "refreshing")
        self.assertEqual(len(payload["rows"]), 1)
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(repository.month_calls[0]["category_codes"], [])

    def test_non_fresh_dependency_reads_do_not_enqueue_when_projection_owns_retry_boundary(self) -> None:
        queue = CaptureRuntimeQueueRepository()
        non_fresh_payload = {
            "read_model_status": "refreshing",
            "rows": [bank_detail_projected_row("txn-001")["payload"]],
            "source_versions": {"bank_detail": 8},
            "read_model_scope_keys": ["2026-05"],
            "read_model_scope_signatures": {
                "2026-05": {"schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}
            },
        }
        repository = FakeBankTaggedReadRepository(
            by_ids_payload=non_fresh_payload,
            snapshot_payload={
                **non_fresh_payload,
                "target_scope_transaction_ids": ["txn-001"],
            },
            scope_summary_payload=non_fresh_payload,
        )
        facade = BankTransactionTagReadFacade(
            read_model_repository=repository,
            queue_repository=queue,
        )

        by_ids = facade.get_by_transaction_ids(
            ["txn-001"],
            require_fresh=False,
            reason="downstream_bank_tag_read",
            month_hint="2026-05",
            scope_keys_hint=["2026-05"],
        )
        source_versions = facade.source_versions_for_scope_keys(
            ["2026-05"],
            require_fresh=False,
            reason="downstream_bank_tag_read",
        )
        snapshot = facade.snapshot_for_month(
            "2026-05",
            include_transaction_ids=["txn-001"],
            require_fresh=False,
            reason="downstream_bank_tag_read",
        )

        self.assertEqual(by_ids["status"], "refreshing")
        self.assertEqual(source_versions["status"], "refreshing")
        self.assertEqual(snapshot["status"], "refreshing")
        self.assertEqual([row["transaction_id"] for row in snapshot["month_rows"]], ["txn-001"])
        self.assertEqual(queue.enqueued, [])


class BankDetailSqlRepositoryTests(unittest.TestCase):
    def test_page_statistics_count_projected_rows_and_reject_inconsistent_payload(self) -> None:
        statistics = _bank_detail_statistics_from_rows(
            [
                {
                    "direction": "income",
                    "effective_category_code": "collection",
                    "relation_status": "linked",
                },
                {
                    "payload": {
                        "direction": "expense",
                        "effective_category_code": "",
                        "relation_status": "unlinked",
                    }
                },
            ]
        )

        self.assertEqual(
            statistics,
            {
                "transaction_count": 2,
                "expense_transaction_count": 1,
                "income_transaction_count": 1,
                "classified_transaction_count": 1,
                "unclassified_transaction_count": 1,
                "linked_transaction_count": 1,
                "unlinked_transaction_count": 1,
            },
        )
        self.assertEqual(_bank_detail_scope_statistics({"statistics": statistics}), statistics)
        invalid = {**statistics, "unlinked_transaction_count": 2}
        self.assertIsNone(_bank_detail_scope_statistics({"statistics": invalid}))

    def test_bank_detail_read_model_port_excludes_unrelated_read_model_methods(self) -> None:
        underlying = _UnderlyingBankDetailReadModelRepository()
        port = BankDetailReadModelRepositoryPort(underlying)

        self.assertEqual(port.bank_detail_scope_keys_for_range(date_from="2026-05-01", date_to=None), ["2026-05"])
        self.assertEqual(port.bank_detail_scope_summary(scope_keys=["2026-05"])["read_model_status"], "fresh")
        self.assertEqual(
            port.bank_detail_category_source_signatures(scope_keys=["2026-05"]),
            {"2026-05": "signature:2026-05"},
        )
        self.assertEqual(
            port.list_bank_detail_transactions(
                account_key=None,
                date_from="2026-05-01",
                date_to=None,
                keyword=None,
                page=1,
                page_size=100,
            )["rows"][0]["id"],
            "txn-1",
        )
        self.assertEqual(port.list_bank_detail_accounts(date_from=None, date_to=None)["accounts"][0]["account_key"], "icbc:6386")
        self.assertEqual(
            port.get_bank_detail_tagged_rows_by_transaction_ids(["txn-1"])["rows"][0]["transaction_id"],
            "txn-1",
        )
        self.assertEqual(
            port.get_bank_detail_tagged_snapshot(
                "2026-05",
                include_transaction_ids=["txn-1"],
            )["rows"][0]["transaction_id"],
            "txn-1",
        )
        self.assertEqual(
            port.list_bank_detail_tagged_rows_by_month("2026-05", direction="expense", category_codes=["fee"])["rows"][0][
                "transaction_id"
            ],
            "txn-1",
        )
        self.assertFalse(hasattr(port, "list_bank_account_balances"))
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "bank_detail_scope_keys_for_range",
                "bank_detail_scope_summary",
                "bank_detail_category_source_signatures",
                "list_bank_detail_transactions",
                "list_bank_detail_accounts",
                "get_bank_detail_tagged_rows_by_transaction_ids",
                "get_bank_detail_tagged_snapshot",
                "list_bank_detail_tagged_rows_by_month",
            ],
        )

    def test_save_bank_detail_rows_keeps_insert_placeholders_aligned_with_record(self) -> None:
        connection = FakeConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_bank_detail_rows(
            scope_key="2026-05",
            rows=[
                {
                    "transaction_id": "txn-001",
                    "trade_time_sort": "2026-05-03T10:00:00+00:00",
                    "category_resolution_status": "auto_matched",
                    "relation_tags": ["oa"],
                    "generated_at": "2026-05-25T00:00:00+00:00",
                    "source_versions": {"source_version": 7},
                }
            ],
        )

        insert_calls = [
            (sql, params)
            for method, sql, params in connection.calls
            if method == "execute_many" and "insert into read_model.bank_detail_rows" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        insert_sql, params_seq = insert_calls[0]
        self.assertEqual(len(params_seq), 1)
        params = params_seq[0]
        columns_match = re.search(
            r"insert into read_model\.bank_detail_rows\s*\((.*?)\)\s*values",
            insert_sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        self.assertIsNotNone(columns_match)
        insert_columns = [column.strip() for column in columns_match.group(1).split(",") if column.strip()]
        placeholder_count = len(re.findall(r"%s", insert_sql))
        self.assertEqual(len(insert_columns), len(params))
        self.assertEqual(placeholder_count, len(params))
        self.assertEqual(len(params), 72)

    def test_scope_keys_for_unbounded_bank_detail_reads_use_month_shards(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    {"scope_key": "2026-04"},
                    {"scope_key": "2026-05"},
                    {"scope_key": "all"},
                    {"scope_key": "bad-scope"},
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        scope_keys = repository.bank_detail_scope_keys_for_range(date_from=None, date_to=None)

        self.assertEqual(scope_keys, ["2026-04", "2026-05"])
        executed_sql = " ".join(call[1].lower() for call in connection.calls)
        self.assertIn("from read_model.bank_detail_scopes", executed_sql)
        self.assertIn("scope_key ~", executed_sql)

    def test_scope_summary_detects_category_source_change_with_one_set_based_query(self) -> None:
        current_signature = "current-category-source-signature"
        connection = FakeConnection(
            rows=[
                [
                    scope_row(
                        "2026-05",
                        source_versions={
                            "source_version": 3,
                            "bank_transaction_category_source_signature": "projected-category-source-signature",
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-05",
                                "relation_count": 0,
                                "relation_updated_at": "",
                            },
                        },
                    ),
                    scope_row(
                        "2026-06",
                        source_versions={
                            "source_version": 4,
                            "bank_transaction_category_source_signature": current_signature,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-06",
                                "relation_count": 0,
                                "relation_updated_at": "",
                            },
                        },
                    ),
                ],
            ],
            category_source_signature_rows=[
                {"scope_key": "2026-05", "source_signature": current_signature},
                {"scope_key": "2026-06", "source_signature": current_signature},
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.bank_detail_scope_summary(scope_keys=["2026-05", "2026-06"])

        self.assertEqual(payload["read_model_status"], "stale")
        signature_calls = [
            (sql, params)
            for method, sql, params in connection.calls
            if method == "fetch_all" and "/* bank_detail_category_source_signatures */" in sql
        ]
        self.assertEqual(len(signature_calls), 1)
        signature_sql, signature_params = signature_calls[0]
        self.assertEqual(signature_params[0], ["2026-05", "2026-06"])
        normalized_sql = " ".join(signature_sql.lower().split())
        self.assertIn("from app.bank_transaction_categories", normalized_sql)
        self.assertIn("from app.bank_transaction_category_confirmations", normalized_sql)
        self.assertIn("digest(", normalized_sql)

    def test_scope_summary_detects_relation_source_change_with_one_set_based_query(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    scope_row(
                        "2026-05",
                        source_versions={
                            "source_version": 3,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-05",
                                "relation_count": 7,
                                "relation_updated_at": "2026-05-25 10:00:00+08",
                            },
                        },
                        raw_payload={
                            "statistics": _bank_detail_statistics_from_rows([])
                        },
                    ),
                    scope_row(
                        "2026-06",
                        source_versions={
                            "source_version": 4,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-06",
                                "relation_count": 3,
                                "relation_updated_at": "2026-06-20 09:00:00+08",
                            },
                        },
                        raw_payload={
                            "statistics": _bank_detail_statistics_from_rows([])
                        },
                    ),
                ],
            ],
            relation_source_summary_rows=[
                {
                    "scope_key": "2026-05",
                    "relation_count": 8,
                    "relation_updated_at": "2026-07-23 16:22:07+08",
                },
                {
                    "scope_key": "2026-06",
                    "relation_count": 3,
                    "relation_updated_at": "2026-06-20 09:00:00+08",
                },
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.bank_detail_scope_summary(scope_keys=["2026-05", "2026-06"])

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["statistics_status"], "stale")
        self.assertEqual(payload["statistics_refresh_scope_keys"], ["2026-05"])
        self.assertEqual(
            payload["read_model_scope_signatures"]["2026-05"]["freshness_status"],
            "stale",
        )
        self.assertEqual(
            payload["read_model_scope_signatures"]["2026-06"]["freshness_status"],
            "fresh",
        )
        relation_summary_calls = [
            (sql, params)
            for method, sql, params in connection.calls
            if method == "fetch_all" and "/* bank_detail_relation_source_summaries */" in sql
        ]
        self.assertEqual(len(relation_summary_calls), 1)
        relation_sql, relation_params = relation_summary_calls[0]
        self.assertEqual(relation_params, (["2026-05-01", "2026-06-01"],))
        normalized_sql = " ".join(relation_sql.lower().split())
        self.assertIn("left join app.workbench_pair_relations", normalized_sql)
        self.assertIn("relation.row_ids && scope.row_ids", normalized_sql)

    def test_scope_summary_detects_canonical_bank_source_change_with_one_set_based_query(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    scope_row(
                        "2026-05",
                        row_count=1,
                        source_versions={
                            "bank_transactions_context_row_count": 1,
                            "bank_transactions_updated_at": "2026-05-03 10:00:00+00",
                        },
                    )
                ],
            ],
            bank_source_summary_rows=[
                {
                    "scope_key": "2026-05",
                    "row_count": 2,
                    "context_row_count": 2,
                    "bank_transactions_updated_at": "2026-07-24 08:00:00+00",
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.bank_detail_scope_summary(scope_keys=["2026-05"])

        self.assertEqual(payload["read_model_status"], "stale")
        source_summary_calls = [
            (sql, params)
            for method, sql, params in connection.calls
            if method == "fetch_all"
            and "/* bank_detail_canonical_source_summaries */" in sql
        ]
        self.assertEqual(len(source_summary_calls), 1)
        source_sql, source_params = source_summary_calls[0]
        self.assertEqual(source_params, (["2026-05"],))
        normalized_sql = " ".join(source_sql.lower().split())
        self.assertIn("left join app.bank_transactions", normalized_sql)
        self.assertIn("interval '2 days'", normalized_sql)

    def test_scope_summary_includes_missing_requested_scope_signature(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    scope_row(
                        "2026-05",
                        source_versions={
                            "source_version": 3,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-05",
                                "relation_count": 0,
                                "relation_updated_at": "",
                            },
                        },
                    ),
                ],
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.bank_detail_scope_summary(
            scope_keys=["2026-05", "2026-06"],
        )

        self.assertEqual(payload["read_model_status"], "missing")
        self.assertEqual(
            payload["read_model_scope_signatures"]["2026-05"]["freshness_status"],
            "fresh",
        )
        self.assertEqual(
            payload["read_model_scope_signatures"]["2026-06"]["freshness_status"],
            "missing",
        )

    def test_scope_summary_keeps_relation_source_current_when_proof_matches(self) -> None:
        relation_proof = {
            "source": "workbench_pair_relations",
            "scope_key": "2026-05",
            "relation_count": 7,
            "relation_updated_at": "2026-05-25 10:00:00+08",
        }
        connection = FakeConnection(
            rows=[
                [
                    scope_row(
                        "2026-05",
                        source_versions={
                            "source_version": 3,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": relation_proof,
                        },
                    )
                ],
            ],
            relation_source_summary_rows=[dict(relation_proof)],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.bank_detail_scope_summary(scope_keys=["2026-05"])

        self.assertEqual(payload["read_model_status"], "fresh")

    def test_transactions_return_none_when_month_scope_is_missing(self) -> None:
        connection = FakeConnection(rows=[[]])
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNone(payload)
        self.assertIn("from read_model.bank_detail_scopes", " ".join(connection.calls[0][1].lower().split()))

    def test_transactions_return_fresh_empty_payload_for_built_empty_scope(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05")],
                {"total": 0},
                [],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 0})

    def test_transactions_filter_uncategorized_rows_by_null_effective_category(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05")],
                {"total": 1},
                [{"category_code": "uncategorized", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-uncategorized",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "供应商",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "普通付款",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "effective_category_code": None,
                            "effective_category_label": None,
                        },
                        "raw_payload": {},
                        "summary": "普通付款",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            category_code="uncategorized",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rows"][0]["id"], "txn-uncategorized")
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("effective_category_code is null", sql_text)
        self.assertNotIn("effective_category_code = %s", sql_text)
        self.assertNotIn("uncategorized", [param for call in connection.calls for param in call[2]])

    def test_get_tagged_rows_by_transaction_ids_reads_only_bank_detail_projection(self) -> None:
        connection = FakeConnection(
            rows=[
                [bank_detail_projected_row("txn-002"), bank_detail_projected_row("txn-001")],
                [scope_row("2026-05")],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_bank_detail_tagged_rows_by_transaction_ids(
            ["txn-001", "txn-missing", "txn-002"]
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual([row["transaction_id"] for row in payload["rows"]], ["txn-001", "txn-002"])
        self.assertEqual(payload["missing_transaction_ids"], ["txn-missing"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(
            payload["source_versions"],
            {
                "source_version": 3,
                "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                "bank_transactions_context_row_count": 0,
                "bank_transactions_updated_at": "",
                "workbench_relation_source_versions": {
                    "source": "workbench_pair_relations",
                    "scope_key": "2026-05",
                    "relation_count": 0,
                    "relation_updated_at": "",
                },
            },
        )
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertIn("transaction_id = any", sql_text)
        self.assertNotIn("from app.bank_transactions", sql_text)

    def test_get_tagged_rows_by_transaction_ids_matches_payload_legacy_ids(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    {
                        **bank_detail_projected_row("uuid-001"),
                        "payload": {
                            **bank_detail_projected_row("legacy-001")["payload"],
                            "id": "legacy-001",
                        },
                    }
                ],
                [scope_row("2026-05")],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_bank_detail_tagged_rows_by_transaction_ids(["legacy-001"])

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual([row["transaction_id"] for row in payload["rows"]], ["legacy-001"])
        self.assertEqual(payload["missing_transaction_ids"], [])
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("payload->>'id' = any", sql_text)
        self.assertIn("payload->>'transaction_id' = any", sql_text)

    def test_get_tagged_snapshot_reads_target_month_and_cross_month_ids_in_one_repeatable_read_snapshot(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    bank_detail_projected_row("txn-month", scope_key="2026-05"),
                    bank_detail_projected_row("txn-cross-month", scope_key="2026-04"),
                ],
                [
                    scope_row(
                        "2026-05",
                        source_version=3,
                        source_versions={
                            "source_version": 3,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-05",
                                "relation_count": 0,
                                "relation_updated_at": "",
                            },
                        },
                    ),
                    scope_row(
                        "2026-04",
                        source_version=2,
                        source_versions={
                            "source_version": 2,
                            "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                            "workbench_relation_source_versions": {
                                "source": "workbench_pair_relations",
                                "scope_key": "2026-04",
                                "relation_count": 0,
                                "relation_updated_at": "",
                            },
                        },
                    ),
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.get_bank_detail_tagged_snapshot(
            "2026-05",
            include_transaction_ids=["txn-cross-month", "txn-missing"],
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(
            [row["transaction_id"] for row in payload["rows"]],
            ["txn-month", "txn-cross-month"],
        )
        self.assertEqual(payload["target_scope_transaction_ids"], ["txn-month"])
        self.assertEqual(payload["missing_transaction_ids"], ["txn-missing"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05", "2026-04"])
        self.assertEqual(
            payload["source_versions"],
            {
                "2026-05": {
                    "source_version": 3,
                    "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                    "bank_transactions_context_row_count": 0,
                    "bank_transactions_updated_at": "",
                    "workbench_relation_source_versions": {
                        "source": "workbench_pair_relations",
                        "scope_key": "2026-05",
                        "relation_count": 0,
                        "relation_updated_at": "",
                    },
                },
                "2026-04": {
                    "source_version": 2,
                    "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                    "bank_transactions_context_row_count": 0,
                    "bank_transactions_updated_at": "",
                    "workbench_relation_source_versions": {
                        "source": "workbench_pair_relations",
                        "scope_key": "2026-04",
                        "relation_count": 0,
                        "relation_updated_at": "",
                    },
                },
            },
        )
        execute_sql = [
            " ".join(sql.lower().split())
            for method, sql, _params in connection.calls
            if method == "execute"
        ]
        self.assertIn("set transaction isolation level repeatable read read only", execute_sql)
        row_query = next(
            " ".join(sql.lower().split())
            for method, sql, _params in connection.calls
            if method == "fetch_all" and "from read_model.bank_detail_rows" in sql.lower()
        )
        self.assertIn("scope_month = %s::date", row_query)
        self.assertIn("transaction_id = any", row_query)
        self.assertIn("payload->>'id' = any", row_query)
        self.assertNotIn("from app.bank_transactions", row_query)

    def test_list_tagged_rows_by_month_uses_direction_and_effective_category_filters(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05")],
                [bank_detail_projected_row("txn-001")],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_tagged_rows_by_month(
            "2026-05",
            direction="expense",
            category_codes=["equipment_purchase"],
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["rows"][0]["effective_category_code"], "equipment_purchase")
        self.assertEqual(
            payload["source_versions"],
            {
                "source_version": 3,
                "bank_transaction_category_source_signature": BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE,
                "bank_transactions_context_row_count": 0,
                "bank_transactions_updated_at": "",
                "workbench_relation_source_versions": {
                    "source": "workbench_pair_relations",
                    "scope_key": "2026-05",
                    "relation_count": 0,
                    "relation_updated_at": "",
                },
            },
        )
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertIn("scope_month = %s::date", sql_text)
        self.assertIn("direction = %s", sql_text)
        self.assertIn("effective_category_code = any", sql_text)
        self.assertNotIn("from app.bank_transactions", sql_text)

    def test_transactions_serve_previous_schema_rows_while_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", schema_version=BANK_DETAIL_READ_MODEL_SCHEMA_VERSION - 1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-old-schema",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "银行",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "手续费",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "auto_category_code": "fee",
                            "auto_category_label": "手续费",
                            "effective_category_code": "fee",
                            "effective_category_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "手续费",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "schema_mismatch")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["rows"][0]["id"], "txn-old-schema")
        self.assertEqual(payload["category_counts"]["fee"], 1)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("schema_version = %s", sql_text)

    def test_transactions_treat_schema_seven_as_mismatch_after_external_turnover_multi_candidate_contract(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", schema_version=7)],
                {"total": 1},
                [{"category_code": "external_turnover", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-old-external-turnover-contract",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "外部候选供应商",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "借出款",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "category_resolution_status": "needs_confirmation",
                            "auto_candidate_categories": [
                                {
                                    "category_code": "external_payment",
                                    "category_primary_label": "外部往来款付款",
                                    "category_sub_label": "借出款",
                                    "category_third_label": "公司往来",
                                }
                            ],
                        },
                        "raw_payload": {},
                        "summary": "借出款",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "schema_mismatch")
        self.assertEqual(payload["rows"][0]["id"], "txn-old-external-turnover-contract")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertNotIn("schema_version = %s", sql_text)

    def test_application_cache_key_includes_bank_detail_schema_version(self) -> None:
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-05"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )
        scope_summary = {
            "read_model_scope_signatures": {
                "2026-05": {
                    "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
                    "source_versions": {"bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION},
                }
            }
        }

        cache_key = service._redis_cache_key("transactions", {"page": 1}, scope_summary=scope_summary)

        expected_signature = {
            "kind": "transactions",
            "query": {"page": 1},
            "scope_signatures": scope_summary["read_model_scope_signatures"],
            "statistics_signature": "missing",
            "schema": f"bank_detail:v{BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}",
        }
        expected_digest = hashlib.sha256(
            json.dumps(expected_signature, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        self.assertEqual(cache_key, f"bank_detail:transactions:{expected_digest}")

    def test_application_statistics_refresh_enqueues_only_reported_stale_scopes(self) -> None:
        class BankDetailRepository:
            @staticmethod
            def bank_detail_scope_keys_for_range(**_kwargs: object) -> list[str]:
                return ["2026-02"]

            @staticmethod
            def bank_detail_scope_summary(*, scope_keys: list[str]) -> dict[str, object]:
                signatures = {
                    scope_key: {
                        "source_versions": {"bank_auto_tag_rules_version": 1},
                    }
                    for scope_key in ("2026-01", "2026-02", "2026-03")
                }
                return {
                    "read_model_status": "fresh",
                    "read_model_scope_keys": list(scope_keys),
                    "read_model_scope_signatures": {
                        "2026-02": signatures["2026-02"]
                    },
                    "statistics": None,
                    "statistics_status": "stale",
                    "statistics_scope_keys": [
                        "2026-01",
                        "2026-02",
                        "2026-03",
                    ],
                    "statistics_refresh_scope_keys": ["2026-02"],
                    "statistics_scope_signatures": signatures,
                }

            @staticmethod
            def list_bank_detail_transactions(**_kwargs: object) -> dict[str, object]:
                return {
                    "read_model_status": "fresh",
                    "rows": [{"id": "txn-1"}],
                    "category_counts": {"uncategorized": 1},
                    "pagination": {"page": 1, "page_size": 20, "total": 1},
                }

        queue = CaptureRuntimeQueueRepository()
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(
                get_bank_auto_tag_rules_payload=lambda **_kwargs: {
                    "version": 1,
                    "active_rules": [],
                }
            ),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=BankDetailRepository(),
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-02"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        payload = service.transactions_payload(
            account_key=None,
            date_from="2026-02-01",
            date_to="2026-02-28",
            keyword=None,
            page=1,
            page_size=20,
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["statistics_status"], "stale")
        self.assertTrue(payload["statistics_refresh_enqueued"])
        self.assertEqual(
            [
                item["scope_key"]
                for item in queue.enqueued
                if item.get("scope_type") == "bank_detail"
            ],
            ["2026-02"],
        )

    def test_application_accounts_uses_account_balance_repository_port(self) -> None:
        class BankDetailRepository:
            def list_bank_account_balances(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("accounts query should use the account balance repository port")

        class AccountBalanceRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_bank_account_balances(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "accounts": [{"account_key": "acct:one"}],
                    "balance_read_model_status": "fresh",
                }

        account_balance_repository = AccountBalanceRepository()
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=BankDetailRepository(),
            bank_account_balance_read_model_repository=account_balance_repository,
            runtime_repositories=SimpleNamespace(),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-05"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        payload = service.accounts_payload(date_from="2026-05-01", date_to="2026-05-31")

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(
            account_balance_repository.calls,
            [{"date_from": "2026-05-01", "date_to": "2026-05-31"}],
        )

    def test_application_transactions_trusts_own_canonical_relation_scope_proof(self) -> None:
        class SqlReadRepository:
            @staticmethod
            def bank_detail_scope_keys_for_range(**_kwargs: object) -> list[str]:
                return ["2026-02", "2026-03"]

            @staticmethod
            def bank_detail_scope_summary(*, scope_keys: list[str]) -> dict[str, object]:
                signatures = {
                    scope_key: {
                        "source_versions": {"bank_auto_tag_rules_version": 1},
                    }
                    for scope_key in scope_keys
                }
                return {
                    "read_model_status": "fresh",
                    "read_model_scope_keys": list(scope_keys),
                    "read_model_scope_signatures": signatures,
                    "statistics_status": "fresh",
                    "statistics_scope_signatures": signatures,
                    "statistics_scope_keys": list(scope_keys),
                    "statistics": _bank_detail_statistics_from_rows([]),
                }

            @staticmethod
            def list_bank_detail_transactions(**_kwargs: object) -> dict[str, object]:
                return {
                    "read_model_status": "fresh",
                    "rows": [],
                    "category_counts": {"uncategorized": 0},
                    "pagination": {"page": 1, "page_size": 100, "total": 0},
                }

        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(
                get_bank_auto_tag_rules_payload=lambda **_kwargs: {"version": 1, "active_rules": []}
            ),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=SqlReadRepository(),
            runtime_repositories=SimpleNamespace(),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-02", "2026-03"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        payload = service.transactions_payload(
            account_key=None,
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=100,
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertNotIn("read_model_dependency_statuses", payload)
        self.assertNotIn("read_model_stale_reasons", payload)

    def test_application_transactions_missing_sql_scope_enqueues_refresh_without_legacy_scan(self) -> None:
        class SqlReadRepository:
            def __init__(self) -> None:
                self.scope_key_calls: list[dict[str, object]] = []
                self.summary_calls: list[list[str]] = []

            def bank_detail_scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
                self.scope_key_calls.append({"date_from": date_from, "date_to": date_to})
                return ["2026-05"]

            def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
                self.summary_calls.append(list(scope_keys))
                return {
                    "read_model_status": "missing",
                    "read_model_scope_keys": list(scope_keys),
                    "read_model_stale_reasons": ["read_model_scope_missing"],
                }

            def list_bank_detail_transactions(self, **_kwargs):
                raise AssertionError("missing bank detail read model must not query rows before refresh")

        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        repository = SqlReadRepository()
        queue = Queue()
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=repository,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-05"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
            bank_transaction_tags_provider=lambda: {"version": 1, "definitions": []},
        )

        payload = service.transactions_payload(
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword=None,
            page=1,
            page_size=500,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["read_model_stale_reasons"], ["read_model_scope_missing"])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 0})
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["refresh_reason"], "api_missing")
        self.assertEqual(queue.enqueued, [("bank_detail", "2026-05", "api_missing")])
        self.assertEqual(repository.scope_key_calls, [{"date_from": "2026-05-01", "date_to": "2026-05-31"}])
        self.assertEqual(repository.summary_calls, [["2026-05"]])

    def test_local_category_mutation_writes_canonical_state_without_read_model_fan_out(self) -> None:
        class CategoryStore:
            def save_bank_transaction_categories(self, _snapshot: dict[str, object]) -> None:
                return None

        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        queue = Queue()
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(snapshot=lambda: {}),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **_kwargs: None),
            bank_transaction_category_store=CategoryStore(),
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        persisted = service._persist_category_mutation(
            ["txn-apr"],
            transaction_id="txn-apr",
            mutation_type="manual_assign",
            actor_id="TESTFULL001",
            action="bank_detail_category_manually_assigned",
            metadata={},
        )

        self.assertEqual(persisted["affected_months"], ["2026-04"])
        self.assertEqual(queue.enqueued, [])

    def test_category_mutation_persists_via_explicit_category_store_port(self) -> None:
        saved_snapshots: list[dict[str, object]] = []

        class CategoryStore:
            def save_bank_transaction_categories(self, snapshot: dict[str, object]) -> None:
                saved_snapshots.append(dict(snapshot))

        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(snapshot=lambda: {"categories": {"txn-apr": {"version": 2}}}),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **_kwargs: None),
            bank_transaction_category_store=CategoryStore(),
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=SimpleNamespace(enqueue_read_model_refresh=lambda **_kwargs: None)),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        persisted = service._persist_category_mutation(
            ["txn-apr"],
            transaction_id="txn-apr",
            mutation_type="manual_assign",
            actor_id="TESTFULL001",
            action="bank_detail_category_manually_assigned",
            metadata={},
        )

        self.assertEqual(persisted["affected_months"], ["2026-04"])
        self.assertEqual(saved_snapshots, [{"categories": {"txn-apr": {"version": 2}}}])

    def test_category_mutation_response_returns_access_scopes_without_operation_barrier(self) -> None:
        class CategoryStore:
            def save_bank_transaction_categories(self, _snapshot: dict[str, object]) -> None:
                return None

        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        queue = Queue()
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(
                get_bank_auto_tag_rules_payload=lambda **_kwargs: {
                    "version": 1,
                    "active_rules": [{"code": "salary"}],
                }
            ),
            bank_transaction_category_service=SimpleNamespace(
                assign_manual_category=lambda **kwargs: {"ok": True, "transaction_id": kwargs["transaction_id"]},
                snapshot=lambda: {},
            ),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **_kwargs: None),
            bank_transaction_category_store=CategoryStore(),
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04", "2026-05"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
            suggestion_provider=lambda _transaction_id: {"category_resolution_status": "unmatched"},
        )

        result = service.assign_manual_category(
            "txn-apr",
            {"category_code": "salary"},
            actor_id="TESTFULL001",
        )

        self.assertEqual(result["affected_months"], ["2026-04"])
        self.assertEqual(result["affected_scope_keys"], ["2026-04"])
        self.assertEqual(result["read_model_scope_keys"], ["2026-04"])
        self.assertNotIn("freshness_targets", result)
        self.assertNotIn("operation_barrier_targets", result)
        self.assertEqual(queue.enqueued, [])

    def test_category_mutation_without_durable_writer_or_local_store_fails_closed(self) -> None:
        queue = SimpleNamespace(enqueue_read_model_refresh=lambda **_kwargs: self.fail("must not enqueue"))
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(
                snapshot=lambda: {},
                get=lambda transaction_id: {"transaction_id": transaction_id},
            ),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **_kwargs: self.fail("must not audit")),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        with self.assertRaisesRegex(RuntimeError, "durable bank transaction category writer is unavailable"):
            service._persist_category_mutation(
                ["txn-apr"],
                transaction_id="txn-apr",
                mutation_type="manual_assign",
                actor_id="TESTFULL001",
                action="bank_detail_category_manually_assigned",
                metadata={},
            )

    def test_category_mutation_writer_suppresses_legacy_fallback_side_effects(self) -> None:
        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        queue = Queue()
        audit_records: list[dict[str, object]] = []
        writer_calls: list[dict[str, object]] = []
        writer = SimpleNamespace(
            persist=lambda **kwargs: writer_calls.append(dict(kwargs))
            or {"changed": True, "affected_months": ["2026-04"], "outbox_event_ids": ["event-1"]}
        )
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(
                snapshot=lambda: {},
                get=lambda transaction_id: {"transaction_id": transaction_id, "category_code": "salary"},
            ),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **kwargs: audit_records.append(dict(kwargs))),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
            category_mutation_writer=writer,
        )

        persisted = service._persist_category_mutation(
            ["txn-apr"],
            transaction_id="txn-apr",
            mutation_type="manual_assign",
            actor_id="TESTFULL001",
            action="bank_detail_category_manually_assigned",
            metadata={"source": "unit"},
        )

        self.assertEqual(persisted["affected_months"], ["2026-04"])
        self.assertEqual(writer_calls[0]["mutation_type"], "manual_assign")
        self.assertEqual(writer_calls[0]["record"]["category_code"], "salary")
        self.assertNotIn("enqueue_refreshes", writer_calls[0])
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(len(audit_records), 1)

    def test_category_mutation_writer_failure_does_not_run_legacy_fallback_side_effects(self) -> None:
        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        queue = Queue()
        audit_records: list[dict[str, object]] = []

        def failing_callback(**_kwargs: object) -> None:
            raise RuntimeError("category_uow_adapter_failed")
        writer = SimpleNamespace(persist=failing_callback)

        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(
                snapshot=lambda: {},
                get=lambda transaction_id: {"transaction_id": transaction_id, "category_code": "salary"},
            ),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(record_action=lambda **kwargs: audit_records.append(dict(kwargs))),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: ["2026-04"],
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
            category_mutation_writer=writer,
        )

        with self.assertRaisesRegex(RuntimeError, "category_uow_adapter_failed"):
            service._persist_category_mutation(
                ["txn-apr"],
                transaction_id="txn-apr",
                mutation_type="manual_assign",
                actor_id="TESTFULL001",
                action="bank_detail_category_manually_assigned",
                metadata={"source": "unit"},
            )

        self.assertEqual(queue.enqueued, [])
        self.assertEqual(audit_records, [])

    def test_auto_tag_rules_update_returns_access_scopes_without_read_model_fan_out(self) -> None:
        class Queue:
            def __init__(self) -> None:
                self.enqueued: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.enqueued.append((scope_type, scope_key, reason))

        queue = Queue()
        update_calls: list[dict[str, object]] = []
        service = BankDetailsApplicationService(
            app_settings_service=SimpleNamespace(
                update_bank_auto_tag_rules=lambda payload, **kwargs: update_calls.append(
                    {"payload": dict(payload), **kwargs}
                )
                or {"version": 12, "active_rules": []}
            ),
            bank_transaction_category_service=SimpleNamespace(),
            bank_transaction_auto_category_service=SimpleNamespace(),
            audit_service=SimpleNamespace(),
            bank_transaction_category_store=None,
            bank_detail_sql_read_repository=None,
            runtime_repositories=SimpleNamespace(queue_repository=queue),
            affected_months_provider=lambda _transaction_ids: [],
            available_month_scope_keys_provider=lambda: ["2026-04", "2026-05"],
            enqueue_bank_account_balance_refresh=lambda **_kwargs: False,
        )

        result = service.update_auto_tag_rules(
            {
                "expected_version": 11,
                "active_rules": [],
                "refresh_scope": {"date_from": "2026-04-01", "date_to": "2026-05-31"},
            },
            actor_id="TESTFULL001",
        )

        self.assertEqual(update_calls[0]["actor_id"], "TESTFULL001")
        self.assertEqual(result["affected_scope_keys"], ["2026-04", "2026-05"])
        self.assertEqual(result["read_model_scope_keys"], ["2026-04", "2026-05"])
        self.assertNotIn("operation_barrier_targets", result)
        self.assertEqual(queue.enqueued, [])

    def test_accounts_serve_previous_schema_rows_while_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", schema_version=BANK_DETAIL_READ_MODEL_SCHEMA_VERSION - 1)],
                [
                    {
                        "account_key": "icbc:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 1,
                        "latest_balance": "90.00",
                        "latest_balance_at": "2026-05-01 10:00:00",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(
            date_from="2026-05-01",
            date_to="2026-05-31",
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "schema_mismatch")
        self.assertEqual(payload["accounts"][0]["account_key"], "icbc:6386")
        self.assertEqual(payload["total_balance"], "90.00")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("schema_version = %s", sql_text)

    def test_transactions_treat_pending_bank_detail_dirty_scope_as_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-refreshing",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "银行",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "手续费",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "auto_category_code": "fee",
                            "auto_category_label": "手续费",
                            "effective_category_code": "fee",
                            "effective_category_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "手续费",
                        "purpose": "",
                    }
                ],
            ],
            dirty_scope_rows=[
                {
                    "scope_key": "2026-05",
                    "status": "pending",
                    "updated_at": "2026-05-27T21:00:00+00:00",
                    "last_error": None,
                    "source_version": 8,
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"][0]["id"], "txn-refreshing")
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        self.assertEqual(payload["dirty_scopes"][0]["scope_key"], "2026-05")
        self.assertEqual(payload["read_model_scope_signatures"]["2026-05"]["dirty_status"], "pending")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from job.read_model_dirty_scopes", sql_text)
        self.assertIn("from read_model.bank_detail_rows", sql_text)

    def test_transactions_rebuild_bank_text_columns_from_raw_payload_or_sql_columns(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=2)],
                {"total": 2},
                [],
                [
                    {
                        "payload": {
                            "id": "txn-fields",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                        },
                        "raw_payload": {
                            "normalized_payload": {
                                "bank_text_fields": [
                                    {"label": "用途", "value": "工行用途"},
                                    {"label": "摘要", "value": "工行摘要"},
                                    {"label": "附言", "value": "工行附言"},
                                ]
                            }
                        },
                        "summary": None,
                        "purpose": None,
                    },
                    {
                        "payload": {
                            "id": "txn-legacy",
                            "bank_name": "建设银行",
                            "account_last4": "8106",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                        },
                        "raw_payload": {},
                        "summary": "SQL摘要",
                        "purpose": "SQL用途",
                    },
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(date_from="2026-05-01", date_to="2026-05-31")

        self.assertIsNotNone(payload)
        rows = {row["id"]: row for row in payload["rows"]}
        self.assertEqual(rows["txn-fields"]["purpose_text"], "工行用途")
        self.assertEqual(rows["txn-fields"]["summary_text"], "工行摘要")
        self.assertEqual(rows["txn-fields"]["note_text"], "工行附言")
        self.assertEqual(rows["txn-legacy"]["purpose_text"], "")
        self.assertEqual(rows["txn-legacy"]["summary_text"], "SQL摘要")
        self.assertEqual(rows["txn-legacy"]["note_text"], "SQL用途")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("select payload, raw_payload, summary, purpose", sql_text)

    def test_transactions_map_legacy_minsheng_text_to_note_only(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-04", row_count=1)],
                {"total": 1},
                [],
                [
                    {
                        "payload": {
                            "id": "txn-cmbc-legacy",
                            "bank_name": "民生银行",
                            "account_last4": "9486",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                            "purpose": "客户附言内容",
                            "summary": "客户附言内容",
                        },
                        "raw_payload": {},
                        "summary": "客户附言内容",
                        "purpose": "客户附言内容",
                    }
                ],
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(date_from="2026-04-01", date_to="2026-04-30")

        self.assertIsNotNone(payload)
        row = payload["rows"][0]
        self.assertEqual(row["purpose_text"], "")
        self.assertEqual(row["summary_text"], "")
        self.assertEqual(row["note_text"], "客户附言内容")

    def test_transactions_filter_by_effective_primary_and_sub_category_labels(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-04", row_count=1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-fee",
                            "effective_category_code": "fee",
                            "effective_category_primary_label": "费用",
                            "effective_category_sub_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "",
                        "purpose": "",
                    }
                ],
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-04-01",
            date_to="2026-04-30",
            category_primary_label="费用",
            category_sub_label="手续费",
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rows"][0]["id"], "txn-fee")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("effective_category_primary_label = %s", sql_text)
        self.assertIn("effective_category_sub_label = %s", sql_text)
        flattened_params = [param for _kind, _sql, params in connection.calls for param in params]
        self.assertIn("费用", flattened_params)
        self.assertIn("手续费", flattened_params)

    def test_transactions_filter_by_effective_third_category_label(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-04", row_count=1)],
                {"total": 1},
                [{"category_code": "external_turnover", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-external",
                            "effective_category_code": "external_turnover",
                            "effective_category_primary_label": "外部往来款付款",
                            "effective_category_sub_label": "借出款",
                            "effective_category_third_label": "公司往来",
                            "effective_category_label_path": ["外部往来款付款", "借出款", "公司往来"],
                        },
                        "raw_payload": {},
                        "summary": "",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-04-01",
            date_to="2026-04-30",
            category_primary_label="外部往来款付款",
            category_sub_label="借出款",
            category_third_label="公司往来",
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rows"][0]["effective_category_label_path"], ["外部往来款付款", "借出款", "公司往来"])
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("effective_category_primary_label = %s", sql_text)
        self.assertIn("effective_category_sub_label = %s", sql_text)
        self.assertIn("effective_category_third_label = %s", sql_text)
        flattened_params = [param for _kind, _sql, params in connection.calls for param in params]
        self.assertIn("公司往来", flattened_params)

    def test_accounts_aggregate_from_bank_detail_rows_only_when_scopes_are_fresh(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=2)],
                [
                    {
                        "account_key": "工商银行:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 2,
                        "latest_balance": "100.25",
                        "latest_balance_at": "2026-05-02 09:00:00",
                    }
                ],
            ],
            bank_source_summary_rows=[
                {
                    "scope_key": "2026-05",
                    "row_count": 2,
                    "context_row_count": 2,
                    "bank_transactions_updated_at": "",
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(date_from="2026-05-01", date_to="2026-05-31")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["accounts"][0]["account_key"], "工商银行:6386")
        self.assertEqual(payload["total_balance"], "100.25")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("from app.bank_transactions", sql_text)

    def test_accounts_use_all_available_rows_for_latest_balances_and_date_range_only_for_counts(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-03", row_count=1)],
                [
                    {
                        "account_key": "工商银行:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 1,
                        "latest_balance": "117644.93",
                        "latest_balance_at": "2026-05-02 09:00:00",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(date_from="2026-03-01", date_to="2026-03-31")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["accounts"][0]["transaction_count"], 1)
        self.assertEqual(payload["accounts"][0]["latest_balance"], "117644.93")
        self.assertEqual(payload["total_balance"], "117644.93")
        account_sql = next(
            " ".join(call[1].lower().split())
            for call in connection.calls
            if "latest_balances" in call[1].lower()
        )
        self.assertIn("filtered as", account_sql)
        self.assertIn("all_rows as", account_sql)
        self.assertIn("from all_rows", account_sql)
        self.assertIn("from filtered", account_sql)


class BankDetailSqlProjectionBuilderTests(unittest.TestCase):
    def test_rebuild_skips_unchanged_scope_and_advances_source_version(self) -> None:
        raw_row = {
            "id": "txn-unchanged",
            "transaction_id": "uuid-unchanged",
            "account_no": "6222000011116386",
            "account_name": "云南溯源科技有限公司",
            "txn_direction": "expense",
            "counterparty_name_raw": "供应商",
            "amount": "100.00",
            "signed_amount": "-100.00",
            "balance": "2138.00",
            "currency": "CNY",
            "txn_date": "2026-05-03",
            "trade_time": "2026-05-03 10:00:00",
            "summary": "普通付款",
            "remark": "",
            "bank_text_fields": [{"label": "摘要", "value": "普通付款"}],
            "raw_payload": {
                "normalized_payload": {
                    "imported_bank_name": "工商银行",
                    "imported_bank_last4": "6386",
                }
            },
            "bank_transaction_updated_at": "2026-05-03 10:00:00+00",
        }
        probe_builder = BankDetailSqlProjectionBuilder(
            connection=FakeConnection(),
            read_model_repository=CaptureBankDetailReadModelRepository(),
        )
        normalized_row = probe_builder._normalize_transaction_row(raw_row)  # noqa: SLF001
        relation_source_versions = {"scope_key": "2026-05", "source_version": 5}
        source_signature = BankDetailSqlProjectionBuilder._source_signature(  # noqa: SLF001
            scope_key="2026-05",
            transaction_rows=[normalized_row],
            auto_category_context_rows=[normalized_row],
            manual_categories={},
        )
        existing_source_versions = {
            "source_version": 8,
            "bank_detail_schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": 1,
            "bank_transaction_category_source_signature": hashlib.sha256(b"{}").hexdigest(),
            "workbench_relation_source_versions": relation_source_versions,
            "bank_detail_source_signature": source_signature,
            "row_count": 1,
            "bank_transactions_context_row_count": 1,
            "bank_transactions_updated_at": "2026-05-03 10:00:00+00",
        }
        existing_statistics = _bank_detail_statistics_from_rows([normalized_row])

        class Repository(CaptureBankDetailReadModelRepository):
            def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
                self.summary_scope_keys = list(scope_keys)
                return {
                    "read_model_scope_signatures": {
                        "2026-05": {
                            "row_count": 1,
                            "source_versions": existing_source_versions,
                            "statistics": existing_statistics,
                        }
                    }
                }

            def workbench_relation_source_versions(self, *, scope_key: str) -> dict[str, object]:
                self.relation_source_scope_key = scope_key
                return relation_source_versions

            def save_bank_detail_rows(
                self,
                *,
                scope_key: str,
                rows: list[dict[str, object]],
                tenant_id: str = "default",
            ) -> None:
                raise AssertionError("unchanged bank detail scope must not rewrite projected rows")

        class RaisingAutoCategoryService:
            def configure_tag_dictionary(self, _payload: dict[str, object]) -> None:
                self.configured = True

            def suggestions_by_transaction_id(self, _rows: list[dict[str, object]]) -> dict[str, object]:
                raise AssertionError("unchanged bank detail scope must not recompute auto categories")

        repository = Repository()
        auto_category_service = RaisingAutoCategoryService()
        connection = FakeConnection(rows=[[raw_row]])
        builder = BankDetailSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
            auto_category_service=auto_category_service,
        )

        result = builder.rebuild_bank_detail_read_model_scope("2026-05", source_version=9)

        self.assertEqual(result["row_count"], 1)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertEqual(repository.summary_scope_keys, ["2026-05"])
        self.assertEqual(repository.relation_source_scope_key, "2026-05")
        self.assertEqual(len(repository.marked_scopes), 1)
        self.assertEqual(repository.marked_scopes[0]["scope_key"], "2026-05")
        self.assertEqual(repository.marked_scopes[0]["row_count"], 1)
        marked_source_versions = repository.marked_scopes[0]["source_versions"]
        self.assertEqual(marked_source_versions["source_version"], 9)
        self.assertEqual(marked_source_versions["bank_detail_source_signature"], source_signature)
        self.assertEqual(marked_source_versions["workbench_relation_source_versions"], relation_source_versions)

    def test_force_refresh_bypasses_unchanged_scope_fast_path(self) -> None:
        class ForceProjectionBuilder(BankDetailSqlProjectionBuilder):
            def _load_transaction_rows_with_auto_category_context(
                self,
                scope_key: str,
            ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
                self.loaded_scope_key = scope_key
                return [], []

            def _configure_auto_category_service_from_app_settings(self) -> None:
                return None

            def _workbench_relation_source_versions_for_scope(
                self,
                scope_key: str,
                *,
                row_ids: list[str] | None = None,
            ) -> dict[str, object]:
                self.relation_source_row_ids = list(row_ids or [])
                return {"scope_key": scope_key, "source_version": 5}

            def _source_versions(self, **kwargs: object) -> dict[str, object]:
                return {"source_version": kwargs.get("source_version"), "row_count": 0}

            def _unchanged_scope_result(self, **_kwargs: object) -> dict[str, object] | None:
                raise AssertionError("force refresh must bypass the unchanged-scope fast path")

        repository = CaptureBankDetailReadModelRepository()
        builder = ForceProjectionBuilder(
            connection=FakeConnection(),
            read_model_repository=repository,
        )

        result = builder.rebuild_bank_detail_read_model_scope(
            "2026-05",
            source_version=9,
            force_refresh=True,
        )

        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(repository.saved_rows, [])
        self.assertEqual(repository.marked_scopes[0]["scope_key"], "2026-05")

    def test_relation_source_summary_tracks_cross_month_members_by_legacy_and_canonical_id(self) -> None:
        class Repository(CaptureBankDetailReadModelRepository):
            def __init__(self) -> None:
                super().__init__()
                self.relation_source_calls: list[dict[str, object]] = []

            def workbench_relation_source_summary_from_source(self, **kwargs: object) -> dict[str, object]:
                self.relation_source_calls.append(dict(kwargs))
                return {
                    "source": "workbench_pair_relations",
                    "scope_key": kwargs.get("scope_key"),
                    "relation_count": 1,
                    "relation_updated_at": "2026-07-13T07:00:00+00:00",
                }

        repository = Repository()
        builder = BankDetailSqlProjectionBuilder(
            connection=FakeConnection(),
            read_model_repository=repository,
            relation_tags_from_source=True,
        )

        result = builder._workbench_relation_source_versions_for_scope(  # noqa: SLF001
            "2026-02",
            row_ids=["txn_imported_1278", "efdb0ec0-9a97-5a0d-9ec4-e4f5eaf918a0"],
        )

        self.assertEqual(result["relation_count"], 1)
        self.assertEqual(
            repository.relation_source_calls,
            [
                {
                    "scope_key": "2026-02",
                    "row_ids": ["txn_imported_1278", "efdb0ec0-9a97-5a0d-9ec4-e4f5eaf918a0"],
                    "include_row_ids": True,
                }
            ],
        )

    def test_rebuild_passes_scope_legacy_and_canonical_ids_to_relation_source_summary(self) -> None:
        class ProjectionBuilder(BankDetailSqlProjectionBuilder):
            def _load_transaction_rows_with_auto_category_context(
                self,
                scope_key: str,
            ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
                row = {"id": "txn_imported_1278", "transaction_id": "canonical-bank-uuid"}
                return [row], [row]

            def _configure_auto_category_service_from_app_settings(self) -> None:
                return None

            def _load_manual_categories(
                self,
                transaction_rows: list[dict[str, object]],
            ) -> dict[str, dict[str, object]]:
                return {}

            def _workbench_relation_source_versions_for_scope(
                self,
                scope_key: str,
                *,
                row_ids: list[str] | None = None,
            ) -> dict[str, object]:
                self.relation_source_call = {"scope_key": scope_key, "row_ids": list(row_ids or [])}
                return {"relation_count": 0, "relation_updated_at": ""}

            def _unchanged_scope_result(self, **kwargs: object) -> dict[str, object] | None:
                return {"scope_key": kwargs["scope_key"], "row_count": kwargs["row_count"], "skipped": True}

        builder = ProjectionBuilder(
            connection=FakeConnection(),
            read_model_repository=CaptureBankDetailReadModelRepository(),
            relation_tags_from_source=True,
        )

        result = builder.rebuild_bank_detail_read_model_scope("2026-02", source_version=11)

        self.assertTrue(result["skipped"])
        self.assertEqual(
            builder.relation_source_call,
            {
                "scope_key": "2026-02",
                "row_ids": ["txn_imported_1278", "canonical-bank-uuid"],
            },
        )

    def test_rebuild_loads_custom_auto_tag_rules_from_app_settings(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            app_settings_payload={
                "bank_transaction_tags": {
                    "version": 2,
                    "definitions": [
                        {
                            "code": "custom_netbank_certificate_service_fee",
                            "label": "网银证书服务费",
                            "path": ["自动识别", "网银证书服务费"],
                            "output_primary_label": "费用",
                            "output_sub_label": "手续费",
                            "source": "custom",
                            "status": "active",
                            "priority": 80,
                            "rule_code": "custom_netbank_certificate_service_fee",
                            "rules": {
                                "match_fields": [
                                    "all_text",
                                    "detail_text",
                                    "note_text",
                                    "summary_text",
                                    "purpose_text",
                                    "counterparty_name",
                                ],
                                "exact": [],
                                "contains": [],
                                "contains_all": ["网银", "服务费"],
                                "excludes": [],
                            },
                        }
                    ],
                },
            },
            rows=[
                [
                    {
                        "id": "txn-netbank-certificate-fee",
                        "transaction_id": "uuid-netbank-certificate-fee",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "中国工商银行云南昆明分行",
                        "amount": "100.00",
                        "signed_amount": "-100.00",
                        "balance": "2138.00",
                        "currency": "CNY",
                        "txn_date": "2026-01-24",
                        "trade_time": "2026-01-24 21:48:34",
                        "summary": "网银证书服务费",
                        "remark": "",
                        "bank_text_fields": [{"label": "摘要", "value": "网银证书服务费"}],
                        "raw_payload": {
                            "normalized_payload": {
                                "imported_bank_name": "工商银行",
                                "imported_bank_last4": "6386",
                            }
                        },
                    }
                ],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-01", source_version=9)

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(repository.saved_rows[0]["auto_category_code"], "custom_netbank_certificate_service_fee")
        self.assertEqual(repository.saved_rows[0]["auto_category_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["auto_category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["auto_category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["auto_category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["category_resolution_status"], "auto_matched")
        self.assertEqual(
            repository.saved_rows[0]["auto_candidate_category_codes"],
            ["custom_netbank_certificate_service_fee"],
        )
        self.assertEqual(repository.saved_rows[0]["manual_confirmed_category_code"], None)
        self.assertEqual(
            repository.saved_rows[0]["category_rule_version"],
            repository.saved_rows[0]["auto_category_rule_version"],
        )
        self.assertEqual(repository.saved_rows[0]["effective_category_code"], "custom_netbank_certificate_service_fee")
        self.assertEqual(repository.saved_rows[0]["effective_category_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["effective_category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["effective_category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["effective_category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["source_versions"]["bank_auto_tag_rules_version"], 2)

    def test_rebuild_enriches_legacy_confirmation_from_current_external_tag_definition(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            app_settings_payload={
                "bank_transaction_tags": {
                    "version": 64,
                    "definitions": [
                        {
                            "code": "custom_borrow_in",
                            "label": "借入款",
                            "path": ["自动识别", "借入款"],
                            "source": "custom",
                            "status": "active",
                            "direction": "income",
                            "output_primary_label": "外部往来款收款",
                            "output_sub_label": "借入款",
                            "turnover_role": "external_turnover",
                            "turnover_action_type": "pending_repayment",
                            "rules": {
                                "match_fields": ["all_text"],
                                "exact": [],
                                "contains": ["暂借款"],
                                "excludes": [],
                            },
                        }
                    ],
                },
            },
            confirmation_rows=[
                {
                    "transaction_id": "txn_imported_1292",
                    "category_code": "custom_borrow_in",
                    "candidate_category_codes": ["custom_borrow_in"],
                    "rule_version": "legacy-rule-version",
                    "version": 5,
                    "raw_payload": {"normalized_payload": {}},
                }
            ],
            rows=[
                [
                    {
                        "id": "txn_imported_1292",
                        "transaction_id": "uuid-1292",
                        "account_no": "6227000011118106",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "贾小花",
                        "amount": "100000.00",
                        "signed_amount": "100000.00",
                        "balance": "3138.00",
                        "currency": "CNY",
                        "txn_date": "2026-02-04",
                        "trade_time": "2026-02-04 17:07:45",
                        "summary": "转账存入",
                        "remark": "暂借款",
                        "bank_text_fields": [{"label": "备注", "value": "暂借款"}],
                        "raw_payload": {
                            "normalized_payload": {
                                "imported_bank_name": "建设银行",
                                "imported_bank_last4": "8106",
                            }
                        },
                    }
                ],
            ],
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-02", source_version=9)

        self.assertEqual(result["row_count"], 1)
        row = repository.saved_rows[0]
        self.assertEqual(row["manual_confirmed_category_code"], "custom_borrow_in")
        self.assertEqual(row["effective_category_code"], "custom_borrow_in")
        self.assertEqual(row["effective_category_primary_label"], "外部往来款收款")
        self.assertEqual(row["effective_category_sub_label"], "借入款")
        self.assertEqual(row["effective_category_label_path"], ["外部往来款收款", "借入款"])
        self.assertEqual(row["effective_turnover_role"], "external_turnover")
        self.assertEqual(row["effective_turnover_action_type"], "pending_repayment")

    def test_rebuild_projects_legacy_external_turnover_third_label_as_confirmation_candidates(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            app_settings_payload={
                "bank_transaction_tags": {
                    "version": 23,
                    "definitions": [
                        {
                            "code": "custom_external_company_borrow_out",
                            "label": "借出款",
                            "path": ["自动识别", "借出款"],
                            "output_primary_label": "外部往来款付款",
                            "output_sub_label": "借出款",
                            "output_third_label": "公司往来",
                            "turnover_action_type": "pending_collection",
                            "source": "custom",
                            "status": "active",
                            "priority": 2,
                            "direction": "expense",
                            "rules": {
                                "match_fields": ["summary_text"],
                                "exact": [],
                                "contains": ["借出周转款"],
                                "excludes": [],
                            },
                        }
                    ],
                },
            },
            rows=[
                [
                    {
                        "id": "txn-external-company-out",
                        "transaction_id": "uuid-external-company-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南路桥",
                        "amount": "8000.00",
                        "signed_amount": "-8000.00",
                        "balance": "2138.00",
                        "currency": "CNY",
                        "txn_date": "2026-01-24",
                        "trade_time": "2026-01-24 21:48:34",
                        "summary": "借出周转款",
                        "remark": "",
                        "bank_text_fields": [{"label": "摘要", "value": "借出周转款"}],
                        "raw_payload": {
                            "normalized_payload": {
                                "imported_bank_name": "工商银行",
                                "imported_bank_last4": "6386",
                            }
                        },
                    }
                ],
                [],
                [],
            ],
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-01", source_version=9)

        self.assertEqual(result["row_count"], 1)
        row = repository.saved_rows[0]
        self.assertIsNone(row["auto_category_code"])
        self.assertEqual(row["category_resolution_status"], "needs_confirmation")
        self.assertIsNone(row["auto_category_third_label"])
        self.assertEqual(row["auto_turnover_action_type"], "pending_collection")
        self.assertEqual(row["auto_turnover_role"], "external_turnover")
        self.assertEqual(
            [candidate["category_third_label"] for candidate in row["auto_candidate_categories"]],
            ["个人往来", "公司往来", "银行往来", "业务往来"],
        )
        self.assertTrue(
            all(
                candidate["category_code"] == "custom_external_company_borrow_out"
                and candidate["category_primary_label"] == "外部往来款付款"
                and candidate["category_sub_label"] == "借出款"
                and candidate["turnover_action_type"] == "pending_collection"
                for candidate in row["auto_candidate_categories"]
            )
        )
        self.assertIsNone(row["effective_category_third_label"])
        self.assertIsNone(row["category_third_label"])
        self.assertIsNone(row["turnover_action_type"])
        self.assertIsNone(row["turnover_family"])

    def test_rebuild_uses_manual_category_for_unmatched_transaction(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            category_rows=[
                {
                    "transaction_id": "txn-manual",
                    "category": "salary",
                    "source": "manual",
                    "version": 1,
                    "raw_payload": {
                        "normalized_payload": {
                            "category_label": "工资",
                            "category_path": ["自动识别", "工资"],
                            "category_primary_label": "费用",
                            "category_sub_label": "工资",
                            "category_label_path": ["费用", "工资"],
                            "manual_assignment": True,
                        }
                    },
                }
            ],
            rows=[
                [
                    {
                        "id": "txn-manual",
                        "transaction_id": "uuid-manual",
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "房克丽",
                        "amount": "160000.00",
                        "signed_amount": "160000.00",
                        "balance": "884077.96",
                        "currency": "CNY",
                        "txn_date": "2026-02-03",
                        "trade_time": "2026-02-03 08:27:06",
                        "summary": "电子汇入",
                        "remark": "电子汇入",
                        "bank_text_fields": [{"label": "摘要", "value": "电子汇入"}],
                        "raw_payload": {
                            "normalized_payload": {
                                "imported_bank_name": "建设银行",
                                "imported_bank_last4": "8106",
                            }
                        },
                    }
                ],
                [],
                [],
            ],
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-02", source_version=9)

        self.assertEqual(result["row_count"], 1)
        row = repository.saved_rows[0]
        self.assertEqual(row["manual_category_code"], "salary")
        self.assertEqual(row["manual_category_source"], "manual")
        self.assertEqual(row["auto_category_code"], None)
        self.assertEqual(row["effective_category_code"], "salary")
        self.assertEqual(row["effective_category_label"], "工资")
        self.assertEqual(row["effective_category_primary_label"], "费用")
        self.assertEqual(row["effective_category_sub_label"], "工资")
        self.assertEqual(row["effective_category_source"], "manual")
        self.assertEqual(row["category_resolution_status"], "manual_confirmed")
        self.assertEqual(row["category_code"], "salary")
        self.assertEqual(row["category_label"], "工资")

    def test_relation_tags_use_workbench_relation_distribution_for_oa_attachment_invoices(self) -> None:
        relation_facade = type(
            "RelationFacade",
            (),
            {
                "last_source_versions": {},
                "list_by_month": lambda _self, *_args, **_kwargs: {
                    "status": "fresh",
                    "rows": [
                        {
                            "row_id": "txn_imported_1242",
                            "group_ids": ["CASE-AUTO-0003"],
                            "linked_oa": [{"id": "oa-exp-1964"}],
                            "linked_input_invoices": [{"id": "oa-att-inv-oa-exp-1964-96685fdf79d36cc6"}],
                            "linked_output_invoices": [],
                        }
                    ],
                    "groups": [],
                    "source_versions": {},
                    "read_model_scope_keys": ["2026-01"],
                    "refresh_enqueued": False,
                    "stale_reasons": [],
                },
            },
        )()
        builder = BankDetailSqlProjectionBuilder(connection=FakeConnection(), workbench_relation_read_facade=relation_facade)

        tags = builder._load_relation_tags(["txn_imported_1242"])  # noqa: SLF001

        self.assertEqual(tags["txn_imported_1242"]["oa_relation_tag"], "有oa")
        self.assertEqual(tags["txn_imported_1242"]["invoice_relation_tag"], "有发票")
        self.assertEqual(tags["txn_imported_1242"]["relation_case_id"], "CASE-AUTO-0003")

    def test_relation_tags_do_not_read_legacy_candidate_matches_in_projection(self) -> None:
        connection = FakeConnection(
            rows=[
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection)

        tags = builder._load_relation_tags(["txn-oa-bank"])  # noqa: SLF001

        self.assertEqual(tags, {})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertNotIn("workbench_candidate_matches", sql_text)

    def test_relation_tags_source_fast_path_does_not_wait_for_relation_read_model(self) -> None:
        class FailingRelationFacade:
            last_source_versions: dict[str, object] = {}

            def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("source fast path must not read relation read model")

        connection = FakeConnection(
            relation_rows=[
                {
                    "case_id": "CASE-SOURCE-001",
                    "status": "active",
                    "row_ids": ["txn-source-1", "oa-source-1", "inv-source-1"],
                    "row_types": ["bank", "oa", "invoice"],
                }
            ],
        )
        builder = BankDetailSqlProjectionBuilder(
            connection=connection,
            workbench_relation_read_facade=FailingRelationFacade(),
            relation_tags_from_source=True,
        )

        tags = builder._load_relation_tags(["txn-source-1"], scope_key="2026-06")  # noqa: SLF001

        self.assertEqual(tags["txn-source-1"]["oa_relation_tag"], "有oa")
        self.assertEqual(tags["txn-source-1"]["invoice_relation_tag"], "有发票")
        self.assertEqual(tags["txn-source-1"]["relation_case_id"], "CASE-SOURCE-001")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from app.workbench_pair_relations", sql_text)

    def test_relation_tags_source_fast_path_resolves_canonical_bank_id_alias(self) -> None:
        self.assertGreaterEqual(BANK_DETAIL_READ_MODEL_SCHEMA_VERSION, 10)
        connection = FakeConnection(
            relation_rows=[
                {
                    "case_id": "CASE-SOURCE-ALIAS",
                    "status": "active",
                    "row_ids": ["uuid-bank-1", "oa-source-1", "inv-source-1"],
                    "row_types": ["bank", "oa", "invoice"],
                }
            ],
        )
        builder = BankDetailSqlProjectionBuilder(
            connection=connection,
            relation_tags_from_source=True,
        )

        tags = builder._load_relation_tags(  # noqa: SLF001
            ["txn_imported_1"],
            scope_key="2026-05",
            transaction_id_aliases={"uuid-bank-1": "txn_imported_1"},
        )

        self.assertEqual(tags["txn_imported_1"]["oa_relation_tag"], "有oa")
        self.assertEqual(tags["txn_imported_1"]["invoice_relation_tag"], "有发票")
        self.assertEqual(tags["txn_imported_1"]["relation_case_id"], "CASE-SOURCE-ALIAS")
        relation_call = next(
            call for call in connection.calls if "from app.workbench_pair_relations" in " ".join(call[1].lower().split())
        )
        self.assertEqual(relation_call[2], (["txn_imported_1", "uuid-bank-1"],))

    def test_normalized_row_splits_bank_text_fields_for_bank_detail_table(self) -> None:
        builder = BankDetailSqlProjectionBuilder(connection=FakeConnection())

        row = builder._normalize_transaction_row(  # noqa: SLF001
            {
                "id": "txn-sql-text",
                "transaction_id": "uuid-sql-text",
                "account_no": "6222000011116386",
                "txn_direction": "expense",
                "counterparty_name_raw": "供应商",
                "amount": "100.00",
                "signed_amount": "-100.00",
                "balance": "900.00",
                "txn_date": "2026-04-23",
                "trade_time": "2026-04-23 17:33:58+08:00",
                "summary": "旧摘要",
                "remark": "旧备注",
                "bank_text_fields": [
                    {"label": "交易用途", "value": "平安交易用途"},
                    {"label": "摘要", "value": "平安摘要"},
                    {"label": "客户附言", "value": "客户附言内容"},
                ],
                "raw_payload": {
                    "normalized_payload": {
                        "imported_bank_name": "平安银行",
                        "imported_bank_last4": "6386",
                    }
                },
            }
        )

        self.assertEqual(row["trade_time"], "2026-04-23 17:33:58")
        self.assertEqual(row["purpose_text"], "平安交易用途")
        self.assertEqual(row["summary_text"], "平安摘要")
        self.assertEqual(row["note_text"], "客户附言内容")

    def test_normalized_row_does_not_copy_missing_bank_columns_from_summary_or_remark(self) -> None:
        builder = BankDetailSqlProjectionBuilder(connection=FakeConnection())

        row = builder._normalize_transaction_row(  # noqa: SLF001
            {
                "id": "txn-sql-cmbc",
                "transaction_id": "uuid-sql-cmbc",
                "account_no": "641979486",
                "txn_direction": "expense",
                "counterparty_name_raw": "供应商",
                "amount": "100.00",
                "signed_amount": "-100.00",
                "balance": "900.00",
                "txn_date": "2026-04-16",
                "trade_time": "2026-04-16 11:09:14+08:00",
                "summary": "旧摘要",
                "remark": "民生客户附言",
                "bank_text_fields": [
                    {"label": "客户附言", "value": "民生客户附言"},
                ],
                "raw_payload": {
                    "normalized_payload": {
                        "imported_bank_name": "民生银行",
                        "imported_bank_last4": "9486",
                    }
                },
            }
        )

        self.assertEqual(row["trade_time"], "2026-04-16 11:09:14")
        self.assertEqual(row["purpose_text"], "")
        self.assertEqual(row["summary_text"], "")
        self.assertEqual(row["note_text"], "民生客户附言")

    def test_rebuild_persists_internal_transfer_auto_category_before_text_category(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-transfer-out",
                        "transaction_id": "uuid-transfer-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                        "amount": "13000.00",
                        "signed_amount": "-13000.00",
                        "balance": "900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 10:00:00",
                        "summary": "手续费",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-transfer-in",
                        "transaction_id": "uuid-transfer-in",
                        "account_no": "6227000011111410",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "云南溯源科技有限公司工商银行账户",
                        "amount": "13000.00",
                        "signed_amount": "13000.00",
                        "balance": "13900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 12:00:00",
                        "summary": "工资",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": "1410"}},
                    },
                ],
                [],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        self.assertEqual(result["row_count"], 2)
        self.assertEqual({row["auto_category_code"] for row in repository.saved_rows}, {"internal_transfer"})
        self.assertEqual({row["effective_category_code"] for row in repository.saved_rows}, {"internal_transfer"})
        self.assertEqual({row["auto_category_label"] for row in repository.saved_rows}, {"内部往来款"})

    def test_rebuild_embeds_internal_transfer_counterpart_summary(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-transfer-out",
                        "transaction_id": "uuid-transfer-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                        "amount": "13000.00",
                        "signed_amount": "-13000.00",
                        "balance": "900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 10:00:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-transfer-in",
                        "transaction_id": "uuid-transfer-in",
                        "account_no": "6227000011111410",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "云南溯源科技有限公司工商银行账户",
                        "amount": "13000.00",
                        "signed_amount": "13000.00",
                        "balance": "13900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 12:00:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": "1410"}},
                    },
                ],
                [],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        rows_by_id = {str(row["id"]): row for row in repository.saved_rows}
        out_counterpart = rows_by_id["txn-transfer-out"]["internal_transfer_counterpart"]
        self.assertEqual(
            out_counterpart,
            {
                "transaction_id": "txn-transfer-in",
                "trade_time": "2026-04-03 12:00:00",
                "bank_name": "建设银行",
                "account_last4": "1410",
                "amount": "13000.00",
                "direction_label": "收",
                "counterparty_name": "云南溯源科技有限公司工商银行账户",
            },
        )
        self.assertEqual(rows_by_id["txn-transfer-out"]["payload"]["internal_transfer_counterpart"], out_counterpart)
        in_counterpart = rows_by_id["txn-transfer-in"]["internal_transfer_counterpart"]
        self.assertEqual(in_counterpart["transaction_id"], "txn-transfer-out")
        self.assertEqual(in_counterpart["bank_name"], "工商银行")
        self.assertEqual(in_counterpart["account_last4"], "6386")
        self.assertEqual(in_counterpart["direction_label"], "支")

    def test_rebuild_uses_boundary_context_for_cross_month_internal_transfer_auto_category(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-transfer-out",
                        "transaction_id": "uuid-transfer-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                        "amount": "13000.00",
                        "signed_amount": "-13000.00",
                        "balance": "900.00",
                        "txn_date": "2026-04-30",
                        "trade_time": "2026-04-30 23:10:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-transfer-in",
                        "transaction_id": "uuid-transfer-in",
                        "account_no": "6227000011111410",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "云南溯源科技有限公司工商银行账户",
                        "amount": "13000.00",
                        "signed_amount": "13000.00",
                        "balance": "13900.00",
                        "txn_date": "2026-05-01",
                        "trade_time": "2026-05-01 00:20:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": "1410"}},
                    },
                ],
                [],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        self.assertEqual(result["row_count"], 1)
        self.assertEqual([row["id"] for row in repository.saved_rows], ["txn-transfer-out"])
        self.assertEqual(repository.saved_rows[0]["auto_category_code"], "internal_transfer")
        self.assertEqual(repository.saved_rows[0]["effective_category_code"], "internal_transfer")


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[str] = []
        self.force_refreshes: list[bool] = []

    def list_bank_detail_scope_shards(self, scope_key: str) -> list[str]:
        self.rebuilt.append(f"list:{scope_key}")
        return ["2026-04", "2026-05"]

    def rebuild_bank_detail_read_model_scope(
        self,
        scope_key: str,
        *,
        source_version: int | None = None,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        self.rebuilt.append(f"rebuild:{scope_key}:{source_version}")
        self.force_refreshes.append(force_refresh)
        return {"scope_key": scope_key, "row_count": 1}


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []
        self.completed: list[tuple[str, str, object]] = []
        self.current_checks: list[tuple[str, str, str, object]] = []
        self.current = True
        self.current_results: list[bool] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str, source_version: object = None) -> bool:
        self.completed.append((scope_type, scope_key, source_version))
        return True

    def read_model_refresh_is_current(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: object,
    ) -> bool:
        self.current_checks.append((tenant_id, scope_type, scope_key, source_version))
        if self.current_results:
            return self.current_results.pop(0)
        return self.current


class BankDetailReadModelRefreshServiceTests(unittest.TestCase):
    def test_all_scope_fans_out_to_month_shards_without_sync_history_rebuild(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("all"))

        self.assertEqual(payload["enqueued_scope_keys"], ["2026-04", "2026-05"])
        self.assertEqual(
            queue.enqueued,
            [
                {"scope_type": "bank_detail", "scope_key": "2026-04", "reason": "bank_detail_all_shard"},
                {"scope_type": "bank_detail", "scope_key": "2026-05", "reason": "bank_detail_all_shard"},
            ],
        )
        self.assertEqual(queue.completed, [("bank_detail", "all", 7)])
        self.assertEqual(builder.rebuilt, ["list:all"])

    def test_month_scope_rebuilds_and_completes_matching_source_version(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("2026-05"))

        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(builder.rebuilt, ["rebuild:2026-05:7"])
        self.assertEqual(builder.force_refreshes, [False])
        self.assertEqual(queue.completed, [("bank_detail", "2026-05", 7)])

    def test_force_refresh_rebuilds_month_scope_without_unchanged_shortcut(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(
            runtime_event("2026-05", metadata={"force_refresh": True}),
        )

        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(builder.rebuilt, ["rebuild:2026-05:7"])
        self.assertEqual(builder.force_refreshes, [True])
        self.assertEqual(queue.completed, [("bank_detail", "2026-05", 7)])

    def test_all_force_refresh_propagates_to_month_shards(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(
            runtime_event("all", metadata={"force_refresh": True}),
        )

        self.assertEqual(payload["enqueued_scope_keys"], ["2026-04", "2026-05"])
        self.assertEqual(
            queue.enqueued,
            [
                {
                    "scope_type": "bank_detail",
                    "scope_key": "2026-04",
                    "reason": "bank_detail_all_shard",
                    "metadata": {"force_refresh": True},
                },
                {
                    "scope_type": "bank_detail",
                    "scope_key": "2026-05",
                    "reason": "bank_detail_all_shard",
                    "metadata": {"force_refresh": True},
                },
            ],
        )
        self.assertEqual(queue.completed, [("bank_detail", "all", 7)])
        self.assertEqual(builder.force_refreshes, [])

    def test_stale_source_version_does_not_rebuild_or_complete(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        queue.current = False
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("2026-05"))

        self.assertEqual(
            payload,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 7,
            },
        )
        self.assertEqual(builder.rebuilt, [])
        self.assertEqual(queue.completed, [])
        self.assertEqual(queue.current_checks, [("default", "bank_detail", "2026-05", 7)])

    def test_source_version_that_becomes_stale_after_rebuild_does_not_complete(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        queue.current_results = [True, False]
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("2026-05"))

        self.assertEqual(
            payload,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version_after_rebuild",
                "source_version": 7,
            },
        )
        self.assertEqual(builder.rebuilt, ["rebuild:2026-05:7"])
        self.assertEqual(queue.completed, [])
        self.assertEqual(
            queue.current_checks,
            [
                ("default", "bank_detail", "2026-05", 7),
                ("default", "bank_detail", "2026-05", 7),
            ],
        )


if __name__ == "__main__":
    unittest.main()
