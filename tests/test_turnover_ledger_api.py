from __future__ import annotations

import json
import os
import pickle
import inspect
from io import BytesIO
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from fin_ops_platform.app.routes_turnover_ledger import TurnoverLedgerApiRoutes
from fin_ops_platform.app.server import Application
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.read_model_freshness import normalize_source_versions
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.turnover_ledger_write_adapters import (
    TurnoverLedgerBankRowTagsRequestBoundaryFacade,
    TurnoverLedgerConfirmRequestBoundaryFacade,
    TurnoverLedgerDirtyOutboxWriter,
    TurnoverLedgerRelationExtraRequestBoundaryFacade,
    TurnoverLedgerTagSelectionRequestBoundaryFacade,
    TurnoverLedgerWithdrawRequestBoundaryFacade,
)
from fin_ops_platform.services.turnover_ledger_read_model_refresh_producer import (
    TurnoverLedgerReadModelRefreshProducer,
)
from fin_ops_platform.services.turnover_ledger_write_facade import TurnoverLedgerWriteFacade


class _QueueRecorder:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class _FailingQueueRecorder:
    def __init__(self) -> None:
        self.attempts: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.attempts.append((scope_type, scope_key, reason))
        raise RuntimeError("queue unavailable")


class _TurnoverReadModelRecorder:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear_turnover_ledger_rows(self) -> None:
        self.clear_calls += 1


class _PostgresFakeTransaction:
    def __init__(self, delegate: object | None = None, pair_relation_service: object | None = None) -> None:
        self._delegate = delegate
        self._pair_relation_service = pair_relation_service
        self.executed: list[dict[str, object]] = []
        self.fetch_all_calls: list[dict[str, object]] = []
        self.fetch_one_calls: list[dict[str, object]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append({"sql": sql, "params": params})
        normalized_sql = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" in normalized_sql:
            snapshot = self._workbench_pair_relation_snapshot()
            relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else {}
            return [
                {"key": str(case_id), "raw_payload": {"normalized_payload": dict(payload)}}
                for case_id, payload in sorted(dict(relations).items())
                if isinstance(payload, dict)
            ]
        if "from app.workbench_pair_relation_history" in normalized_sql:
            snapshot = self._workbench_pair_relation_snapshot()
            history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else []
            return [
                {"raw_payload": {"normalized_payload": dict(item)}}
                for item in list(history or [])
                if isinstance(item, dict)
            ]
        if "from app.bank_transactions" in normalized_sql and "scope_key" in normalized_sql:
            return [{"scope_key": "2026-02"}, {"scope_key": "2026-03"}]
        return []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append({"sql": sql, "params": params})
        return {"source_version": len(self.fetch_one_calls)}

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed.append({"sql": sql, "params": params})

    def _workbench_pair_relation_snapshot(self) -> dict[str, object]:
        loader = getattr(self._delegate, "load_workbench_pair_relations", None)
        if callable(loader):
            snapshot = loader()
            relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            if isinstance(relations, dict):
                return snapshot
        pair_snapshot = getattr(self._pair_relation_service, "snapshot", None)
        if callable(pair_snapshot):
            snapshot = pair_snapshot()
            return snapshot if isinstance(snapshot, dict) else {}
        return {}


class _PostgresFakeConnection:
    def __init__(self, delegate: object | None = None, pair_relation_service: object | None = None) -> None:
        self.transaction_obj = _PostgresFakeTransaction(delegate, pair_relation_service)

    @contextmanager
    def transaction(self) -> object:
        yield self.transaction_obj


class _PostgresLikeStateStore:
    storage_backend = "postgres"

    def __init__(self, delegate: object, pair_relation_service: object | None = None) -> None:
        self._delegate = delegate
        self._connection = _PostgresFakeConnection(delegate, pair_relation_service)

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


class _PostgresQueueRecorder:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []
        self.transactional: list[tuple[str, str, str, object]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.enqueued.append((scope_type, scope_key, reason))

    def enqueue_read_model_refresh_in_transaction(
        self,
        *,
        transaction: object,
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, priority, trace_id, metadata
        self.transactional.append((scope_type, scope_key, reason, transaction))
        return {"scope_type": scope_type, "scope_key": scope_key, "reason": reason, "source_version": len(self.transactional)}

    def enqueue_read_model_refreshes_in_transaction(
        self,
        *,
        transaction: object,
        refreshes: list[dict[str, object]],
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> list[dict[str, object]]:
        return [
            self.enqueue_read_model_refresh_in_transaction(
                transaction=transaction,
                scope_type=str(refresh.get("scope_type") or ""),
                scope_key=str(refresh.get("scope_key") or ""),
                reason=str(refresh.get("reason") or ""),
                tenant_id=tenant_id,
                priority=priority,
                trace_id=trace_id,
                metadata=dict(refresh.get("metadata") or {}),
            )
            for refresh in refreshes
        ]


class _RelationExtraWriteFacadeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def update_relation_extra(
        self,
        *,
        relation_id: str,
        payload: dict[str, object],
        actor_id: str,
        tenant_id: str,
        scope_keys: list[str],
        expected_versions: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        call = {
            "relation_id": relation_id,
            "payload": dict(payload),
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "scope_keys": list(scope_keys),
            "expected_versions": dict(expected_versions or {}),
        }
        if idempotency_key is not None:
            call["idempotency_key"] = idempotency_key
        self.calls.append(call)
        return {
            "extra": {
                "relation_id": relation_id,
                "note": payload.get("note"),
                "updated_by": actor_id,
            },
            "row": {"relation_id": relation_id, "note": payload.get("note")},
        }


class _RelationWriteFacadeRecorder:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []
        self.withdraw_calls: list[dict[str, object]] = []

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.confirm_calls.append(
            {
                "bank_row_ids": list(bank_row_ids),
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "note": note,
                "affected_months": list(affected_months),
                "expected_versions": dict(expected_versions or {}),
            }
        )
        return {
            "relation": {
                "relation_id": "turnover_rel_facade_confirm",
                "status": "confirmed",
                "source": "manual",
            }
        }

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor_id: str,
        tenant_id: str,
        note: str | None,
        affected_months: list[str],
        expected_versions: dict[str, object] | None = None,
    ) -> dict[str, object]:
        self.withdraw_calls.append(
            {
                "relation_id": relation_id,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "note": note,
                "affected_months": list(affected_months),
                "expected_versions": dict(expected_versions or {}),
            }
        )
        return {
            "relation": {
                "relation_id": relation_id,
                "status": "withdrawn",
                "source": "manual",
            }
        }


class _BankRowTagsWriteFacadeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def update_bank_row_tags_batch(
        self,
        *,
        updates: list[dict[str, object]],
        actor_id: str,
        tenant_id: str,
        affected_months: list[str],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "updates": [dict(update) for update in list(updates or [])],
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "affected_months": list(affected_months),
            }
        )
        return {"updated": len(list(updates or []))}


class _RecordingTurnoverLedgerUow:
    def __init__(self) -> None:
        self.commands: list[object] = []

    def run(self, command: object, handler: object) -> dict[str, object]:
        self.commands.append(command)
        _ = handler
        return {"ok": True}


class TurnoverLedgerApiTests(unittest.TestCase):
    def test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction(self) -> None:
        queue = _PostgresQueueRecorder()
        transaction = _PostgresFakeTransaction()
        writer = TurnoverLedgerDirtyOutboxWriter(queue_repository=queue)

        events = writer.enqueue_refreshes(
            transaction=transaction,
            refreshes=[
                {
                    "scope_type": "cost_statistics",
                    "scope_keys": ["2026-02", "all"],
                    "reason": "import_state_changed",
                }
            ],
        )

        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [
                ("cost_statistics", "active:2026-02", "import_state_changed"),
                ("cost_statistics", "all:2026-02", "import_state_changed"),
                ("cost_statistics", "active:all", "import_state_changed"),
                ("cost_statistics", "all:all", "import_state_changed"),
            ],
        )
        self.assertEqual(
            [event["scope_key"] for event in events],
            ["active:2026-02", "all:2026-02", "active:all", "all:all"],
        )
        self.assertNotIn(
            ("cost_statistics", "2026-02", "import_state_changed", transaction),
            queue.transactional,
        )
        self.assertNotIn(
            ("cost_statistics", "all", "import_state_changed", transaction),
            queue.transactional,
        )

    @contextmanager
    def _without_default_test_auth(self):
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_missing(self) -> None:
        row = {
            "id": "bank-row-manual-version",
            "effective_category_code": "external_personal",
            "effective_turnover_action_type": "personal_advance",
            "effective_turnover_family": "personal",
            "direction": "income",
            "amount": "100.00",
            "trade_time": "2026-02-03T10:11:12",
            "counterparty_name": "张三",
            "manual_category_version": 9,
        }

        turnover_row = Application._turnover_bank_transaction_row_from_bank_detail(row)

        self.assertIsNotNone(turnover_row)
        self.assertEqual(turnover_row["category_version"], 9)

    def test_sql_bank_detail_turnover_row_uses_manual_category_version_when_category_version_is_zero(self) -> None:
        row = {
            "id": "bank-row-zero-category-version",
            "effective_category_code": "external_personal",
            "effective_turnover_action_type": "personal_advance",
            "effective_turnover_family": "personal",
            "direction": "income",
            "amount": "100.00",
            "trade_time": "2026-02-03T10:11:12",
            "counterparty_name": "张三",
            "category_version": 0,
            "manual_category_version": 9,
        }

        turnover_row = Application._turnover_bank_transaction_row_from_bank_detail(row)

        self.assertIsNotNone(turnover_row)
        self.assertEqual(turnover_row["category_version"], 9)

    def test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_versions_missing(self) -> None:
        row = {
            "id": "bank-row-base-version",
            "effective_category_code": "external_personal",
            "effective_turnover_action_type": "personal_advance",
            "effective_turnover_family": "personal",
            "direction": "expense",
            "amount": "100.00",
            "trade_time": "2026-02-03T10:11:12",
            "counterparty_name": "张三",
            "version": 5,
        }

        turnover_row = Application._turnover_bank_transaction_row_from_bank_detail(row)

        self.assertIsNotNone(turnover_row)
        self.assertEqual(turnover_row["category_version"], 5)

    def test_sql_bank_detail_turnover_row_falls_back_to_bank_row_version_when_category_version_is_zero(self) -> None:
        row = {
            "id": "bank-row-zero-category-base-version",
            "effective_category_code": "external_personal",
            "effective_turnover_action_type": "personal_advance",
            "effective_turnover_family": "personal",
            "direction": "expense",
            "amount": "100.00",
            "trade_time": "2026-02-03T10:11:12",
            "counterparty_name": "张三",
            "category_version": 0,
            "version": 5,
        }

        turnover_row = Application._turnover_bank_transaction_row_from_bank_detail(row)

        self.assertIsNotNone(turnover_row)
        self.assertEqual(turnover_row["category_version"], 5)

    def test_sql_bank_detail_turnover_row_prefers_category_version_over_manual_version(self) -> None:
        row = {
            "id": "bank-row-category-version",
            "effective_category_code": "external_personal",
            "effective_turnover_action_type": "personal_advance",
            "effective_turnover_family": "personal",
            "direction": "income",
            "amount": "100.00",
            "trade_time": "2026-02-03T10:11:12",
            "counterparty_name": "张三",
            "category_version": 3,
            "manual_category_version": 9,
        }

        turnover_row = Application._turnover_bank_transaction_row_from_bank_detail(row)

        self.assertIsNotNone(turnover_row)
        self.assertEqual(turnover_row["category_version"], 3)

    def _import_bank_rows(self, app: Application) -> list[str]:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank.xlsx",
            imported_by="YNSYLP005",
            rows=[
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-02-04",
                    "trade_time": "2026-02-04 13:23:17",
                    "pay_receive_time": "2026-02-04 13:23:17",
                    "counterparty_name": "梁希涛",
                    "debit_amount": "",
                    "credit_amount": "200000.00",
                    "summary": "电子汇入",
                    "remark": "暂借款",
                    "imported_bank_name": "建行",
                    "imported_bank_last4": "8106",
                },
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-05",
                    "trade_time": "2026-03-05 09:34:42",
                    "pay_receive_time": "2026-03-05 09:34:42",
                    "counterparty_name": "梁希涛",
                    "debit_amount": "100000.00",
                    "credit_amount": "",
                    "summary": "还暂借款",
                    "remark": "还款",
                    "imported_bank_name": "建行",
                    "imported_bank_last4": "8106",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        return [transaction.id for transaction in app._import_service.list_transactions()]

    def _tag_rows(
        self,
        app: Application,
        transaction_ids: list[str],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        _ = headers
        app._bank_transaction_category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_ids[0],
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": transaction_ids[1],
                    "category_code": "borrow_in_company_repaid",
                    "expected_version": 0,
                },
            ],
            actor="test",
        )
        app._turnover_ledger_service._category_provider = None
        app._turnover_ledger_service._selected_tag_codes_provider = None
        app._state_store.save_bank_transaction_categories(app._bank_transaction_category_service.snapshot())
        app._turnover_ledger_service.list_ledger()
        app._state_store.save_turnover_relations(app._turnover_relation_service.snapshot())

    def _seed_turnover_tag_selection_settings(self, data_dir: Path) -> None:
        ApplicationStateStore(data_dir).save_app_settings(
            {
                "bank_transaction_tags": {
                    "version": 1,
                    "definitions": [
                        {
                            "code": "external_rule_borrow_out",
                            "label": "借出款",
                            "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                            "source": "custom",
                            "status": "active",
                            "output_primary_label": "外部往来款付款",
                            "output_sub_label": "借出款",
                            "turnover_role": "external_turnover",
                            "turnover_action_type": "pending_collection",
                            "direction": "any",
                            "account_scope": {"type": "any", "values": []},
                            "rules": {
                                "match_fields": ["all_text"],
                                "contains_any": ["借出"],
                                "contains_all": [],
                                "exact_any": [],
                                "regex_any": [],
                                "none_of": [],
                            },
                        },
                        {
                            "code": "external_rule_repaid",
                            "label": "归还借款",
                            "path": ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
                            "source": "custom",
                            "status": "active",
                            "output_primary_label": "外部往来款付款",
                            "output_sub_label": "归还借款",
                            "turnover_role": "external_turnover",
                            "turnover_action_type": "repaid",
                            "direction": "any",
                            "account_scope": {"type": "any", "values": []},
                            "rules": {
                                "match_fields": ["all_text"],
                                "contains_any": ["归还"],
                                "contains_all": [],
                                "exact_any": [],
                                "regex_any": [],
                                "none_of": [],
                            },
                        },
                    ],
                },
                "turnover_ledger_tag_selection": {
                    "version": 1,
                    "selected_tag_codes": ["external_rule_borrow_out"],
                },
            }
        )

    def _seed_turnover_rows(self, app: Application, category_by_transaction_id: dict[str, str]) -> None:
        rows: list[dict[str, object]] = []
        for transaction in app._import_service.list_transactions(month="all"):
            payload = app._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            transaction_id = str(payload.get("id") or "").strip()
            category_code = category_by_transaction_id.get(transaction_id)
            if not category_code:
                continue
            row = dict(payload)
            row["category_code"] = category_code
            amount = row.get("amount") or "0.00"
            direction = str(row.get("txn_direction") or "").strip().lower()
            row["debit_amount"] = amount if direction == "outflow" else "0.00"
            row["credit_amount"] = amount if direction == "inflow" else "0.00"
            row["counterparty_name"] = str(row.get("counterparty_name_raw") or row.get("counterparty_name") or "")
            rows.append(row)
        app._turnover_relation_service.rebuild_from_bank_rows(rows)
        app._state_store.save_turnover_relations(app._turnover_relation_service.snapshot())

    def _import_and_tag_business_row(self, app: Application) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="business-bank.xlsx",
            imported_by="YNSYLP005",
            rows=[
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-06",
                    "trade_time": "2026-03-06 10:00:00",
                    "pay_receive_time": "2026-03-06 10:00:00",
                    "counterparty_name": "昆明建设集团",
                    "debit_amount": "5000.00",
                    "credit_amount": "",
                    "summary": "质保金",
                    "remark": "项目A",
                    "imported_bank_name": "交行",
                    "imported_bank_last4": "3847",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        transaction_id = app._import_service.list_transactions()[-1].id
        app._bank_transaction_category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_id,
                    "category_code": "business_warranty_pending_collection",
                    "expected_version": 0,
                }
            ],
            actor="test",
        )
        app._turnover_ledger_service._category_provider = None
        app._turnover_ledger_service._selected_tag_codes_provider = None
        app._state_store.save_bank_transaction_categories(app._bank_transaction_category_service.snapshot())
        app._turnover_ledger_service.list_ledger()
        app._state_store.save_turnover_relations(app._turnover_relation_service.snapshot())
        return transaction_id

    def test_get_turnover_ledger_returns_summary_rows_and_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)

            response = app.handle_request("GET", "/api/turnover-ledger?family=company&status=suggested")
            payload = json.loads(response.body)
            relation_id = payload["rows"][0]["relation_id"]
            detail_response = app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}")
            detail_payload = json.loads(detail_response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(payload["summary"]["pending_repayment_amount"], "100000.00")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["family"], "company")
        self.assertEqual(payload["rows"][0]["status"], "suggested")
        self.assertEqual(detail_payload["relation"]["relation_id"], relation_id)
        self.assertEqual(len(detail_payload["bank_rows"]), 2)

    def test_get_turnover_ledger_enqueues_refresh_for_stale_sql_read_model_source_versions(self) -> None:
        class StaleTurnoverReadRepository:
            def __init__(self) -> None:
                self.saved_payload: dict[str, object] | None = None

            def list_turnover_ledger_view(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "rows": [{"relation_id": "stale_sql_row", "counterparty_name": "旧读模型"}],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "filters": {},
                    "read_model_status": "fresh",
                    "source_versions": {"turnover_ledger_schema_version": "old"},
                }

            def save_turnover_ledger_rows(self, payload: dict[str, object], **_kwargs: object) -> None:
                self.saved_payload = payload

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            repository = StaleTurnoverReadRepository()
            queue = _QueueRecorder()
            app._workbench_sql_read_repository = repository
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._turnover_ledger_query_service._read_repository = repository
            app._turnover_ledger_query_service._refresh_queue_repository = queue

            response = app.handle_request("GET", "/api/turnover-ledger")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rows"][0]["relation_id"], "stale_sql_row")
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertIn(("turnover_ledger", "all", "api_stale"), queue.enqueued)
        self.assertIsNone(repository.saved_payload)

    def test_get_turnover_ledger_grouped_preserves_fresh_sql_read_model_metadata(self) -> None:
        class FreshTurnoverReadRepository:
            def __init__(self, source_versions: dict[str, object]) -> None:
                self.source_versions = source_versions

            def list_turnover_ledger_view(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"pending_repayment_amount": "100000.00", "row_count": 1},
                    "family_summaries": [],
                    "rows": [
                        {
                            "relation_id": "fresh_sql_relation",
                            "counterparty_name": "SQL对方",
                            "family": "company",
                            "family_label": "公司往来",
                            "status": "suggested",
                            "amount": "100000.00",
                            "pending_repayment_amount": "100000.00",
                            "source_versions": dict(self.source_versions),
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "filters": {},
                    "read_model_status": "fresh",
                    "source_versions": dict(self.source_versions),
                }

            def save_turnover_ledger_rows(self, payload: dict[str, object], **_kwargs: object) -> None:
                raise AssertionError("GET must not save turnover ledger rows")

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            source_versions = app._turnover_ledger_source_versions()
            repository = FreshTurnoverReadRepository(source_versions)
            queue = _QueueRecorder()
            app._turnover_ledger_query_service._read_repository = repository
            app._turnover_ledger_query_service._refresh_queue_repository = queue

            response = app.handle_request("GET", "/api/turnover-ledger?view=grouped&family=company")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(payload["source_versions"], normalize_source_versions(source_versions))
        self.assertIn("groups", payload)
        self.assertEqual(payload["groups"][0]["counterparty_name"], "SQL对方")
        self.assertEqual(queue.enqueued, [])

    def test_get_turnover_ledger_grouped_preserves_stale_sql_refresh_metadata(self) -> None:
        class StaleTurnoverReadRepository:
            def list_turnover_ledger_view(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"row_count": 1},
                    "family_summaries": [],
                    "rows": [
                        {
                            "relation_id": "stale_sql_relation",
                            "counterparty_name": "旧SQL对方",
                            "family": "company",
                            "family_label": "公司往来",
                            "status": "suggested",
                            "amount": "100000.00",
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "filters": {},
                    "read_model_status": "fresh",
                    "source_versions": {"turnover_ledger_schema_version": "old"},
                }

            def save_turnover_ledger_rows(self, payload: dict[str, object], **_kwargs: object) -> None:
                raise AssertionError("GET must not save turnover ledger rows")

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            repository = StaleTurnoverReadRepository()
            queue = _QueueRecorder()
            app._turnover_ledger_query_service._read_repository = repository
            app._turnover_ledger_query_service._refresh_queue_repository = queue

            response = app.handle_request("GET", "/api/turnover-ledger?view=grouped&family=company")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertEqual(payload["groups"][0]["counterparty_name"], "旧SQL对方")
        self.assertIn(("turnover_ledger", "all", "api_stale"), queue.enqueued)

    def test_get_turnover_ledger_grouped_view_returns_groups(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)

            response = app.handle_request("GET", "/api/turnover-ledger?view=grouped&family=company")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", payload)
        self.assertEqual(payload["filters"]["family"], "company")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["groups"][0]["counterparty_name"], "梁希涛")
        self.assertEqual(payload["groups"][0]["family"], "company")
        self.assertIn("summary_row", payload["groups"][0])
        self.assertIn("flow_rows", payload["groups"][0])
        self.assertIn("allocation_lots", payload["groups"][0])
        self.assertIn("lot_rows", payload["groups"][0])
        self.assertIsInstance(payload["groups"][0]["flow_rows"], list)
        self.assertIsInstance(payload["groups"][0]["allocation_lots"], list)
        self.assertIsInstance(payload["groups"][0]["lot_rows"], list)
        self.assertEqual(payload["groups"][0]["summary_row"]["row_kind"], "summary")
        self.assertEqual(payload["groups"][0]["summary_row"]["display_level"], "group_summary")
        self.assertEqual(payload["groups"][0]["row_span"], 1 + len(payload["groups"][0]["flow_rows"]))
        self.assertNotIn("rows", payload)
        self.assertNotIn("rows", payload["groups"][0])

    def test_turnover_cash_closure_withdraw_route_uses_closure_boundary(self) -> None:
        class FakeClosureBoundary:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def withdraw_cash_closure_case_from_request(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "status": "withdrawn",
                    "workbench_pair_relation": {
                        "case_id": kwargs["cash_closure_case_id"],
                        "relation_mode": "manual_confirmed",
                    },
                    "affected_months": ["2026-05"],
                    "freshness_targets": [
                        {"read_model_key": "turnover_ledger", "scope_key": "2026-05"},
                        {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
                    ],
                }

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            boundary = FakeClosureBoundary()
            app._turnover_ledger_closure_request_boundary_facade = lambda: boundary  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/withdraw",
                body=json.dumps({
                    "cash_closure_case_id": "case-workbench-cash-1",
                    "note": "撤回关联台闭环",
                    "idempotency_key": "withdraw-cash-1",
                }),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["status"], "withdrawn")
        self.assertEqual(payload["workbench_pair_relation"]["case_id"], "case-workbench-cash-1")
        self.assertEqual(payload["freshness_targets"][1], {"read_model_key": "workbench_relation", "scope_key": "2026-05"})
        self.assertEqual(boundary.calls[0]["cash_closure_case_id"], "case-workbench-cash-1")
        self.assertEqual(boundary.calls[0]["note"], "撤回关联台闭环")
        self.assertEqual(boundary.calls[0]["idempotency_key"], "withdraw-cash-1")

    def test_confirmed_external_turnover_rule_enters_ledger_with_default_selection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ApplicationStateStore(Path(temp_dir)).save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "external_rule_borrow_out",
                                "label": "借出款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "借出款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "pending_collection",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["借出"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            }
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 1,
                        "groups": {
                            "requires_invoice": {"tag_codes": []},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )
            app = build_application(data_dir=Path(temp_dir))
            preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="external-turnover.xlsx",
                imported_by="YNSYLP005",
                rows=[
                    {
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司基本户",
                        "txn_date": "2026-03-06",
                        "trade_time": "2026-03-06 10:00:00",
                        "counterparty_name": "昆明建设集团",
                        "debit_amount": "5000.00",
                        "credit_amount": "",
                        "summary": "借出周转款",
                        "remark": "项目A",
                    }
                ],
            )
            app._import_service.confirm_import(preview.id)
            transaction_id = app._import_service.list_transactions()[0].id

            before_response = app.handle_request("GET", "/api/turnover-ledger")
            confirm_response = app.handle_request(
                "POST",
                f"/api/bank-details/transactions/{transaction_id}/category-confirmation",
                body=json.dumps({"category_code": "external_rule_borrow_out", "category_third_label": "公司往来"}),
            )
            flat_response = app.handle_request("GET", "/api/turnover-ledger")
            grouped_response = app.handle_request("GET", "/api/turnover-ledger?view=grouped&family=company")
            before_payload = json.loads(before_response.body)
            flat_payload = json.loads(flat_response.body)
            grouped_payload = json.loads(grouped_response.body)
            app.shutdown_background_jobs()

        self.assertEqual(before_response.status_code, 200)
        self.assertEqual(before_payload["pagination"]["total"], 0)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(flat_response.status_code, 200)
        self.assertEqual(flat_payload["pagination"]["total"], 1)
        self.assertEqual(flat_payload["rows"][0]["family"], "company")
        self.assertEqual(flat_payload["rows"][0]["category_codes"], ["external_rule_borrow_out"])
        self.assertEqual(grouped_response.status_code, 200)
        self.assertEqual(grouped_payload["pagination"]["total"], 1)
        flow = grouped_payload["groups"][0]["flow_rows"][0]
        self.assertEqual(flow["category_primary_label"], "外部往来款付款")
        self.assertEqual(flow["category_sub_label"], "借出款")
        self.assertEqual(flow["category_third_label"], "公司往来")
        self.assertEqual(flow["category_label_path"], ["外部往来款付款", "借出款", "公司往来"])

    def test_turnover_ledger_tag_selection_get_put_and_version_conflict(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ApplicationStateStore(Path(temp_dir)).save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "external_rule_borrow_out",
                                "label": "借出款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "借出款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "pending_collection",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["借出"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            },
                            {
                                "code": "external_rule_repaid",
                                "label": "归还借款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "归还借款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "repaid",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["归还"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            },
                            {
                                "code": "fee",
                                "label": "手续费",
                                "path": ["费用", "手续费"],
                                "source": "system",
                                "status": "active",
                                "output_primary_label": "费用",
                                "output_sub_label": "手续费",
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 1,
                        "groups": {
                            "requires_invoice": {"tag_codes": []},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )
            app = build_application(data_dir=Path(temp_dir))
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request("GET", "/api/turnover-ledger/tag-selection")
            payload = json.loads(response.body)
            save_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(
                    {
                        "expected_version": payload["version"],
                        "selected_tag_codes": ["external_rule_borrow_out"],
                    }
                ),
            )
            saved_payload = json.loads(save_response.body)
            conflict_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(
                    {
                        "expected_version": payload["version"],
                        "selected_tag_codes": ["external_rule_borrow_out"],
                    }
                ),
            )
            invalid_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(
                    {
                        "expected_version": saved_payload["version"],
                        "selected_tag_codes": ["fee"],
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {tag["code"] for tag in payload["active_tags"]},
            {"external_rule_borrow_out", "external_rule_repaid"},
        )
        self.assertIsInstance(payload["version"], int)
        self.assertIn("version", payload)
        self.assertIn("selected_tag_codes", payload)
        self.assertIn("active_tags", payload)
        self.assertEqual(
            {
                "code": payload["active_tags"][0]["code"],
                "label": payload["active_tags"][0]["label"],
                "turnover_action_type": payload["active_tags"][0]["turnover_action_type"],
            },
            {
                "code": "external_rule_borrow_out",
                "label": "借出款",
                "turnover_action_type": "pending_collection",
            },
        )
        self.assertEqual(set(payload["selected_tag_codes"]), {"external_rule_borrow_out", "external_rule_repaid"})
        self.assertEqual(save_response.status_code, 200)
        self.assertIsInstance(saved_payload["version"], int)
        self.assertEqual(saved_payload["selected_tag_codes"], ["external_rule_borrow_out"])
        self.assertEqual(
            {tag["code"] for tag in saved_payload["active_tags"]},
            {"external_rule_borrow_out", "external_rule_repaid"},
        )
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "turnover_ledger_tag_selection_version_conflict")
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(json.loads(invalid_response.body)["error"], "invalid_turnover_ledger_tag")
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")])
        self.assertEqual(read_repository.clear_calls, 0)

    def test_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ApplicationStateStore(Path(temp_dir)).save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "external_rule_borrow_out",
                                "label": "借出款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "借出款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "pending_collection",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["借出"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            },
                            {
                                "code": "external_rule_repaid",
                                "label": "归还借款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "归还借款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "repaid",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["归还"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            },
                        ],
                    },
                    "pending_invoice_tag_groups": {
                        "version": 1,
                        "groups": {
                            "requires_invoice": {"tag_codes": []},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        },
                    },
                }
            )
            app = build_application(data_dir=Path(temp_dir))
            queue = _FailingQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "PUT",
                    "/api/turnover-ledger/tag-selection",
                    body=json.dumps(
                        {
                            "expected_version": initial_payload["version"],
                            "selected_tag_codes": ["external_rule_borrow_out"],
                        }
                    ),
                )
            restored_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.attempts, [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")])
        self.assertEqual(restored_payload["selected_tag_codes"], initial_payload["selected_tag_codes"])
        self.assertEqual(restored_payload["version"], initial_payload["version"])

    def test_target_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ApplicationStateStore(Path(temp_dir)).save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "external_rule_borrow_out",
                                "label": "借出款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "借出款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "pending_collection",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["借出"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            }
                        ],
                    },
                    "turnover_ledger_tag_selection": {
                        "version": 1,
                        "selected_tag_codes": ["external_rule_borrow_out"],
                    },
                }
            )
            app = build_application(data_dir=Path(temp_dir))
            queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "PUT",
                    "/api/turnover-ledger/tag-selection",
                    body=json.dumps(
                        {
                            "expected_version": initial_payload["version"],
                            "selected_tag_codes": [],
                        }
                    ),
                )
            restored_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

        self.assertEqual(restored_payload["selected_tag_codes"], initial_payload["selected_tag_codes"])
        self.assertEqual(restored_payload["version"], initial_payload["version"])

    def test_target_turnover_ledger_tag_selection_uow_path_does_not_clear_read_model_directly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ApplicationStateStore(Path(temp_dir)).save_app_settings(
                {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {
                                "code": "external_rule_borrow_out",
                                "label": "借出款",
                                "path": ["银行明细自动标签规则", "外部往来款付款", "借出款"],
                                "source": "custom",
                                "status": "active",
                                "output_primary_label": "外部往来款付款",
                                "output_sub_label": "借出款",
                                "turnover_role": "external_turnover",
                                "turnover_action_type": "pending_collection",
                                "direction": "any",
                                "account_scope": {"type": "any", "values": []},
                                "rules": {
                                    "match_fields": ["all_text"],
                                    "contains_any": ["借出"],
                                    "contains_all": [],
                                    "exact_any": [],
                                    "regex_any": [],
                                    "none_of": [],
                                },
                            }
                        ],
                    },
                    "turnover_ledger_tag_selection": {
                        "version": 1,
                        "selected_tag_codes": ["external_rule_borrow_out"],
                    },
                }
            )
            app = build_application(data_dir=Path(temp_dir))
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

            response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(
                    {
                        "expected_version": initial_payload["version"],
                        "selected_tag_codes": [],
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")])
        self.assertEqual(read_repository.clear_calls, 0)

    def test_turnover_ledger_tag_selection_handler_does_not_inline_legacy_fallback_side_effects(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_tag_selection_update_route)

        self.assertNotIn("update_turnover_ledger_tag_selection(", source)
        self.assertNotIn("_clear_turnover_ledger_read_model_best_effort(", source)
        self.assertNotIn("_enqueue_turnover_ledger_read_model_refreshes(", source)
        self.assertIn("facade = self._tag_selection_write_boundary_provider()", source)
        self.assertIn("result = facade.update_tag_selection_from_request(", source)
        self.assertNotIn('scope_keys=["all"]', source)

    def test_turnover_ledger_tag_selection_request_boundary_facade_wires_write_facade(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_tag_selection_request_boundary_facade)

        self.assertIn("TurnoverLedgerTagSelectionRequestBoundaryFacade(", source)
        self.assertIn("facade_provider=self._turnover_ledger_tag_selection_write_facade", source)

    def test_turnover_ledger_tag_selection_request_boundary_fails_fast_without_write_facade(self) -> None:
        facade = TurnoverLedgerTagSelectionRequestBoundaryFacade(facade_provider=lambda: None)

        with self.assertRaisesRegex(RuntimeError, "turnover tag selection write facade is unavailable"):
            facade.update_tag_selection_from_request(
                payload={"selected_tag_codes": ["borrow_in_company_pending_repayment"]},
                actor_id="user-1",
                tenant_id="default",
            )

    def test_turnover_ledger_tag_selection_write_facade_does_not_inline_local_snapshot_closures(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_tag_selection_write_facade)

        self.assertNotIn("settings_snapshot_provider=lambda", source)
        self.assertNotIn("save_snapshot = lambda", source)

    def test_turnover_ledger_primary_write_facades_no_longer_construct_uow_in_server(self) -> None:
        methods = [
            Application._turnover_ledger_relation_extra_write_facade,
            Application._turnover_ledger_bank_row_tags_write_facade,
            Application._turnover_ledger_confirm_write_facade,
            Application._turnover_ledger_withdraw_write_facade,
            Application._turnover_ledger_tag_selection_write_facade,
        ]

        for method in methods:
            with self.subTest(method=method.__name__):
                source = inspect.getsource(method)
                self.assertIn("state_store = getattr(self, \"_state_store\", None)", source)
                self.assertIn("queue_repository = self._turnover_ledger_write_queue_repository(state_store)", source)
                self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", source)

    def test_turnover_ledger_primary_write_facades_no_longer_inline_placeholder_ports_or_default_stale_precondition(self) -> None:
        relation_extra_source = inspect.getsource(Application._turnover_ledger_relation_extra_write_facade)
        self.assertNotIn("relation_repository=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("settings_port=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("bankdetail_port=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None)", relation_extra_source)

    def test_turnover_ledger_tag_selection_primary_write_facade_uses_builder_boundary(self) -> None:
        tag_selection_source = inspect.getsource(Application._turnover_ledger_tag_selection_write_facade)
        self.assertIn("TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder(", tag_selection_source)
        self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", tag_selection_source)
        self.assertNotIn("relation_repository=SimpleNamespace()", tag_selection_source)
        self.assertNotIn("extra_repository=SimpleNamespace()", tag_selection_source)
        self.assertNotIn("bankdetail_port=SimpleNamespace()", tag_selection_source)

    def test_turnover_ledger_withdraw_primary_write_facade_uses_builder_boundary(self) -> None:
        withdraw_source = inspect.getsource(Application._turnover_ledger_withdraw_write_facade)
        self.assertIn("TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder(", withdraw_source)
        self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", withdraw_source)
        self.assertNotIn("extra_repository=SimpleNamespace()", withdraw_source)
        self.assertNotIn("settings_port=SimpleNamespace()", withdraw_source)
        self.assertNotIn("bankdetail_port=SimpleNamespace()", withdraw_source)

    def test_turnover_ledger_confirm_primary_write_facade_uses_builder_boundary(self) -> None:
        confirm_source = inspect.getsource(Application._turnover_ledger_confirm_write_facade)
        self.assertIn("TurnoverLedgerConfirmPrimaryWriteFacadeBuilder(", confirm_source)
        self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", confirm_source)
        self.assertNotIn("extra_repository=SimpleNamespace()", confirm_source)
        self.assertNotIn("settings_port=SimpleNamespace()", confirm_source)
        self.assertNotIn("bankdetail_port=SimpleNamespace()", confirm_source)

    def test_turnover_ledger_bank_row_tags_primary_write_facade_uses_builder_boundary(self) -> None:
        bank_row_tags_source = inspect.getsource(Application._turnover_ledger_bank_row_tags_write_facade)
        self.assertIn("TurnoverLedgerBankRowTagsPrimaryWriteFacadeBuilder(", bank_row_tags_source)
        self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", bank_row_tags_source)
        self.assertNotIn("relation_repository=SimpleNamespace()", bank_row_tags_source)
        self.assertNotIn("extra_repository=SimpleNamespace()", bank_row_tags_source)
        self.assertNotIn("settings_port=SimpleNamespace()", bank_row_tags_source)

    def test_turnover_ledger_relation_extra_primary_write_facade_uses_builder_boundary(self) -> None:
        relation_extra_source = inspect.getsource(Application._turnover_ledger_relation_extra_write_facade)
        self.assertIn("TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder(", relation_extra_source)
        self.assertNotIn("TurnoverLedgerWriteUnitOfWork(", relation_extra_source)
        self.assertNotIn("relation_repository=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("settings_port=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("bankdetail_port=SimpleNamespace()", relation_extra_source)
        self.assertNotIn("_workbench_write_idempotency_store(", relation_extra_source)
        self.assertNotIn("InMemoryWorkbenchIdempotencyRepository()", relation_extra_source)

    def test_turnover_ledger_primary_write_facades_use_local_runtime_support_boundary(self) -> None:
        methods = [
            Application._turnover_ledger_relation_extra_write_facade,
            Application._turnover_ledger_bank_row_tags_write_facade,
            Application._turnover_ledger_confirm_write_facade,
            Application._turnover_ledger_withdraw_write_facade,
        ]

        for method in methods:
            with self.subTest(method=method.__name__):
                source = inspect.getsource(method)
                self.assertIn("support = self._turnover_ledger_local_runtime_support()", source)

    def test_relation_extra_write_facade_keeps_expected_versions_and_durable_idempotency_contract(self) -> None:
        uow = _RecordingTurnoverLedgerUow()
        facade = TurnoverLedgerWriteFacade(
            uow=uow,
            extra_normalizer=lambda relation_id, payload, actor_id: {
                "relation_id": relation_id,
                "note": payload.get("note"),
                "updated_by": actor_id,
            },
        )

        facade.update_relation_extra(
            relation_id="turnover_rel_consistency",
            payload={"note": "keep-contract"},
            actor_id="actor-1",
            tenant_id="tenant-1",
            expected_versions={"turnover_relation_extra:turnover_rel_consistency": "v1"},
            idempotency_key=" idem-1 ",
        )

        command = uow.commands[0]
        self.assertEqual(command.action_name, "turnover_relation_extra_update")
        self.assertEqual(
            command.expected_versions,
            {"turnover_relation_extra:turnover_rel_consistency": "v1"},
        )
        self.assertEqual(command.idempotency_key, "idem-1")
        self.assertTrue(command.request_fingerprint)
        self.assertEqual(
            command.refresh_requests,
            [{"scope_type": "turnover_ledger", "scope_keys": ["all"], "reason": "turnover_relation_extra_changed"}],
        )

    def test_withdraw_write_facade_keeps_expected_versions_but_has_no_durable_idempotency_contract(self) -> None:
        uow = _RecordingTurnoverLedgerUow()
        facade = TurnoverLedgerWriteFacade(uow=uow)

        facade.withdraw_relation(
            relation_id="turnover_rel_withdraw_consistency",
            actor_id="actor-1",
            tenant_id="tenant-1",
            note="withdraw",
            affected_months=["2026-02", "2026-03"],
            expected_versions={"relation:turnover_rel_withdraw_consistency": 3},
        )

        command = uow.commands[0]
        self.assertEqual(command.action_name, "withdraw_relation")
        self.assertEqual(command.expected_versions, {"relation:turnover_rel_withdraw_consistency": 3})
        self.assertEqual(command.idempotency_key, "")
        self.assertEqual(command.request_fingerprint, "")
        self.assertEqual(
            command.refresh_requests,
            [
                {
                    "scope_type": "turnover_ledger",
                    "scope_keys": ["2026-02", "2026-03"],
                    "reason": "turnover_relation_changed",
                },
                {
                    "scope_type": "workbench",
                    "scope_keys": ["2026-02", "2026-03"],
                    "reason": "turnover_relation_changed",
                },
                {
                    "scope_type": "workbench_relation",
                    "scope_keys": ["2026-02", "2026-03"],
                    "reason": "turnover_relation_changed",
                },
                {
                    "scope_type": "cost_statistics",
                    "scope_keys": ["active:2026-02", "active:2026-03"],
                    "reason": "cost_statistics_relation_delta",
                },
                {
                    "scope_type": "search",
                    "scope_keys": ["2026-02", "2026-03"],
                    "reason": "turnover_relation_changed",
                },
            ],
        )

    def test_withdraw_stale_precondition_rejects_changed_relation_before_mutation_or_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before stale withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            current_detail = app._turnover_ledger_api_routes.get_relation(relation_id)
            stale_detail = {
                **current_detail,
                "relation": {**dict(current_detail["relation"]), "version": 1},
            }
            changed_detail = {
                **current_detail,
                "relation": {**dict(current_detail["relation"]), "version": 2},
            }
            get_relation_calls: list[str] = []

            def get_relation_with_version_change(requested_relation_id: str) -> dict[str, object]:
                get_relation_calls.append(requested_relation_id)
                if len(get_relation_calls) == 1:
                    return stale_detail
                return changed_detail

            app._turnover_ledger_api_routes.get_relation = get_relation_with_version_change  # type: ignore[method-assign]
            queue.enqueued.clear()
            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "stale withdraw should fail"}),
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "turnover_relation_conflict")
        self.assertEqual(get_relation_calls, [relation_id, relation_id])
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [("confirm_relation", "confirmed")],
        )
        self.assertEqual(queue.enqueued, [])

    def test_confirm_stale_bank_row_precondition_rejects_before_mutation_or_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(
                    {
                        "bank_row_ids": transaction_ids,
                        "note": "stale confirm should fail",
                        "expected_versions": {
                            f"turnover_bank_row:{transaction_ids[0]}": 0,
                        },
                    }
                ),
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "turnover_relation_conflict")
        self.assertEqual(audit_log, [])
        self.assertEqual(queue.enqueued, [])

    def test_confirm_write_facade_currently_has_no_stale_precondition_or_durable_idempotency_contract(self) -> None:
        uow = _RecordingTurnoverLedgerUow()
        facade = TurnoverLedgerWriteFacade(uow=uow)

        facade.confirm_relation(
            bank_row_ids=["txn-1", "txn-2"],
            actor_id="actor-1",
            tenant_id="tenant-1",
            note="confirm",
            affected_months=["2026-02"],
        )

        command = uow.commands[0]
        self.assertEqual(command.action_name, "confirm_relation")
        self.assertEqual(command.expected_versions, {})
        self.assertEqual(command.idempotency_key, "")
        self.assertEqual(command.request_fingerprint, "")

    def test_confirm_request_body_without_expected_versions_keeps_empty_write_command_versions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            uow = _RecordingTurnoverLedgerUow()
            app._turnover_ledger_confirm_write_facade_override = TurnoverLedgerWriteFacade(uow=uow)

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(
                    {
                        "bank_row_ids": transaction_ids,
                        "note": "confirm legacy payload has no expected versions",
                    }
                ),
            )
            command = uow.commands[0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(command.action_name, "confirm_relation")
        self.assertEqual(command.expected_versions, {})
        self.assertEqual(command.idempotency_key, "")
        self.assertEqual(command.request_fingerprint, "")

    def test_target_confirm_request_expected_versions_reach_write_command(self) -> None:
        expected_versions = {"turnover_bank_row:bank-txn-confirm-1": "v1"}
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            uow = _RecordingTurnoverLedgerUow()
            app._turnover_ledger_confirm_write_facade_override = TurnoverLedgerWriteFacade(uow=uow)

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(
                    {
                        "bank_row_ids": transaction_ids,
                        "note": "target confirm expected versions",
                        "expected_versions": expected_versions,
                    }
                ),
            )
            command = uow.commands[0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(command.action_name, "confirm_relation")
        self.assertEqual(command.expected_versions, expected_versions)

    def test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            request_body = {
                "bank_row_ids": transaction_ids,
                "note": "idempotent confirm",
                "idempotency_key": "confirm-idem-1",
            }

            first_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(request_body),
            )
            second_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(request_body),
            )
            first_payload = json.loads(first_response.body)
            second_payload = json.loads(second_response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_payload["relation"]["relation_id"], first_payload["relation"]["relation_id"])
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [("confirm_relation", "confirmed")],
        )
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_target_confirm_idempotency_key_conflict_rejects_different_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            first_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(
                    {
                        "bank_row_ids": transaction_ids,
                        "note": "first idempotent confirm",
                        "idempotency_key": "confirm-idem-conflict",
                    }
                ),
            )
            conflict_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps(
                    {
                        "bank_row_ids": transaction_ids,
                        "note": "different idempotent confirm",
                        "idempotency_key": "confirm-idem-conflict",
                    }
                ),
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "idempotency_key_conflict")
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [("confirm_relation", "confirmed")],
        )
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_bank_row_tags_write_facade_without_idempotency_key_keeps_empty_idempotency_contract(self) -> None:
        uow = _RecordingTurnoverLedgerUow()
        facade = TurnoverLedgerWriteFacade(uow=uow)

        facade.update_bank_row_tags_batch(
            updates=[{"transaction_id": "txn-1", "category_code": "borrow_out_company_lent"}],
            actor_id="actor-1",
            tenant_id="tenant-1",
            affected_months=["2026-02"],
        )

        command = uow.commands[0]
        self.assertEqual(command.action_name, "bank_row_tags_batch")
        self.assertEqual(command.expected_versions, {})
        self.assertEqual(command.idempotency_key, "")
        self.assertEqual(command.request_fingerprint, "")

    def test_tag_selection_write_facade_currently_has_no_stale_precondition_or_durable_idempotency_contract(self) -> None:
        uow = _RecordingTurnoverLedgerUow()
        facade = TurnoverLedgerWriteFacade(
            uow=uow,
            tag_selection_normalizer=lambda payload, actor_id: {
                "public_payload": {"selected_tag_codes": list(payload.get("selected_tag_codes") or [])},
                "next_selection": {"selected_tag_codes": list(payload.get("selected_tag_codes") or [])},
                "next_snapshot": {"version": 2, "selected_tag_codes": list(payload.get("selected_tag_codes") or [])},
                "audit_event": {"actor_id": actor_id, "selected_tag_codes": list(payload.get("selected_tag_codes") or [])},
            },
        )

        facade.update_tag_selection(
            payload={"selected_tag_codes": ["external_rule_borrow_out"]},
            actor_id="actor-1",
            tenant_id="tenant-1",
        )

        command = uow.commands[0]
        self.assertEqual(command.action_name, "turnover_ledger_tag_selection_changed")
        self.assertEqual(command.expected_versions, {})
        self.assertEqual(command.idempotency_key, "")
        self.assertEqual(command.request_fingerprint, "")

    def test_turnover_ledger_primary_write_builders_still_use_local_and_postgres_dirty_outbox_split(self) -> None:
        builder_sources = {
            "relation_extra": inspect.getsource(Application._turnover_ledger_relation_extra_write_facade),
            "withdraw": inspect.getsource(Application._turnover_ledger_withdraw_write_facade),
            "confirm": inspect.getsource(Application._turnover_ledger_confirm_write_facade),
            "bank_row_tags": inspect.getsource(Application._turnover_ledger_bank_row_tags_write_facade),
            "tag_selection": inspect.getsource(Application._turnover_ledger_tag_selection_write_facade),
        }

        for name, source in builder_sources.items():
            with self.subTest(builder=name):
                self.assertIn("PrimaryWriteFacadeBuilder(", source)

        adapter_source = inspect.getsource(Application._turnover_ledger_relation_extra_write_facade.__globals__["TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder"].build)
        self.assertIn("TurnoverLedgerDirtyOutboxWriter(", adapter_source)
        self.assertIn("TurnoverLedgerLocalDirtyOutboxWriter(", adapter_source)

        withdraw_builder_source = inspect.getsource(
            Application._turnover_ledger_withdraw_write_facade.__globals__["TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder"].build
        )
        self.assertIn("TurnoverLedgerDirtyOutboxWriter(", withdraw_builder_source)
        self.assertIn("TurnoverLedgerLocalDirtyOutboxWriter(", withdraw_builder_source)

    def test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service(self) -> None:
        sources = {
            "closure": inspect.getsource(Application._turnover_ledger_closure_write_facade),
            "withdraw": inspect.getsource(Application._turnover_ledger_withdraw_write_facade),
        }

        for name, source in sources.items():
            with self.subTest(source=name):
                self.assertIn("relation_command_service_factory=self._turnover_workbench_relation_command_service", source)
                self.assertIn("relation_facade=self._workbench_relation_read_facade()", source)
        self.assertFalse(hasattr(Application, "_turnover_ledger_closure_legacy_fallback_facade"))
        self.assertFalse(hasattr(Application, "_turnover_ledger_withdraw_legacy_fallback_facade"))

    def test_turnover_ledger_primary_write_builders_still_use_noop_local_stale_precondition_ports(self) -> None:
        builder_methods = [
            Application._turnover_ledger_tag_selection_write_facade.__globals__["TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder"].build,
            Application._turnover_ledger_bank_row_tags_write_facade.__globals__["TurnoverLedgerBankRowTagsPrimaryWriteFacadeBuilder"].build,
        ]

        for build_method in builder_methods:
            with self.subTest(builder=build_method.__qualname__):
                source = inspect.getsource(build_method)
                self.assertIn("stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None)", source)

    def test_target_relation_extra_primary_builder_uses_explicit_stale_precondition_port(self) -> None:
        # PF-P186 target contract: request-boundary stale checks are a compatibility
        # guard; relation extra's primary UoW path should enforce the precondition
        # inside the same transaction before extra repository save and dirty/outbox.
        source = inspect.getsource(
            Application._turnover_ledger_relation_extra_write_facade.__globals__[
                "TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder"
            ].build
        )

        self.assertNotIn("stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None)", source)
        self.assertRegex(source, r"RelationExtra.*StalePreconditionPort")

    def test_turnover_ledger_withdraw_builder_uses_relation_stale_precondition_port(self) -> None:
        source = inspect.getsource(
            Application._turnover_ledger_withdraw_write_facade.__globals__["TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder"].build
        )

        self.assertIn("TurnoverLedgerRelationStalePreconditionPort(", source)
        self.assertIn("relation_detail_provider=self._routes.get_relation", source)
        self.assertNotIn("stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None)", source)

    def test_turnover_ledger_confirm_builder_reuses_bank_row_selection_for_stale_check_and_preview(self) -> None:
        source = inspect.getsource(
            Application._turnover_ledger_confirm_write_facade.__globals__["TurnoverLedgerConfirmPrimaryWriteFacadeBuilder"].build
        )

        self.assertIn("TurnoverLedgerBankRowSelectionPort(", source)
        self.assertIn("bank_rows_by_ids_provider=bank_row_selection_port.rows_by_ids", source)
        self.assertIn("stale_precondition_port = bank_row_selection_port", source)
        self.assertIn("bank_rows_provider=self._bank_rows_provider", source)
        self.assertNotIn("stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None)", source)

    def test_turnover_ledger_local_runtime_helpers_delegate_to_support_boundary(self) -> None:
        helper_names = [
            "_postgres_turnover_ledger_persistence_repository",
            "_replace_local_bank_transaction_category_snapshot",
            "_replace_local_turnover_relation_snapshot",
            "_replace_local_turnover_ledger_extra_snapshot",
            "_save_local_bank_transaction_categories_snapshot",
            "_save_local_turnover_relations_snapshot",
            "_save_local_turnover_ledger_extras_snapshot",
        ]

        for helper_name in helper_names:
            with self.subTest(helper_name=helper_name):
                source = inspect.getsource(getattr(Application, helper_name))
                self.assertIn("_turnover_ledger_local_runtime_support()", source)

    def test_replace_local_bank_transaction_category_snapshot_rebinds_dependent_services(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            original_category_service = app._bank_transaction_category_service
            snapshot = original_category_service.snapshot()

            app._replace_local_bank_transaction_category_snapshot(snapshot)

        self.assertIsNot(app._bank_transaction_category_service, original_category_service)
        self.assertIs(app._app_settings_service._bank_transaction_category_service, app._bank_transaction_category_service)
        self.assertIs(app._bank_details_service._category_service, app._bank_transaction_category_service)
        self.assertIs(app._turnover_ledger_service._category_service, app._bank_transaction_category_service)
        self.assertIs(app._turnover_ledger_service._category_provider, app._bank_transaction_effective_category_provider)
        self.assertIs(app._live_workbench_service._category_provider, app._bank_transaction_effective_category_provider)

    def test_replace_local_turnover_relation_snapshot_rebinds_routes_and_service(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            original_relation_service = app._turnover_relation_service
            snapshot = original_relation_service.snapshot()

            app._replace_local_turnover_relation_snapshot(snapshot)

        self.assertIsNot(app._turnover_relation_service, original_relation_service)
        self.assertIs(app._turnover_ledger_service._relation_service, app._turnover_relation_service)
        self.assertIs(app._turnover_ledger_api_routes._relation_service, app._turnover_relation_service)

    def test_replace_local_turnover_ledger_extra_snapshot_rebinds_routes_and_service(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            original_extra_service = app._turnover_ledger_extra_service
            snapshot = app._turnover_ledger_api_routes.extras_snapshot()

            app._replace_local_turnover_ledger_extra_snapshot(snapshot)

        self.assertIsNot(app._turnover_ledger_extra_service, original_extra_service)
        self.assertIs(app._turnover_ledger_api_routes._extra_service, app._turnover_ledger_extra_service)
        self.assertIs(app._turnover_ledger_service._extra_service, app._turnover_ledger_extra_service)

    def test_local_tag_selection_adapter_uses_only_domain_settings_boundary(self) -> None:
        adapter_type = Application._turnover_ledger_tag_selection_write_facade.__globals__[
            "TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder"
        ].build.__globals__["TurnoverLedgerLocalTagSelectionAdapterSet"]
        source = inspect.getsource(adapter_type)

        self.assertIn("get_turnover_ledger_tag_selection_state", source)
        self.assertIn("commit_turnover_ledger_tag_selection_update", source)
        self.assertIn("restore_turnover_ledger_tag_selection_state", source)
        self.assertNotIn("_snapshot", source)
        self.assertNotIn("save_app_settings", source)

    def test_turnover_ledger_local_save_helpers_require_state_store_methods(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            for helper, expected_message in (
                (app._save_local_bank_transaction_categories_snapshot, "save_bank_transaction_categories"),
                (app._save_local_turnover_relations_snapshot, "save_turnover_relations"),
                (app._save_local_turnover_ledger_extras_snapshot, "save_turnover_ledger_extras"),
            ):
                with self.subTest(helper=helper.__name__):
                    with self.assertRaisesRegex(RuntimeError, expected_message):
                        helper(object(), {})

    def test_turnover_ledger_local_save_helpers_keep_best_effort_warning_contract(self) -> None:
        class FailingCategoryStore:
            def save_bank_transaction_categories(self, snapshot: dict[str, object]) -> None:
                _ = snapshot
                raise RuntimeError("category store unavailable")

        class FailingRelationStore:
            def save_turnover_relations(self, snapshot: dict[str, object]) -> None:
                _ = snapshot
                raise RuntimeError("relation store unavailable")

        class FailingExtraStore:
            def save_turnover_ledger_extras(self, snapshot: dict[str, object]) -> None:
                _ = snapshot
                raise RuntimeError("extra store unavailable")

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            warnings: list[dict[str, object]] = []
            app._emit_workbench_persistence_warning = lambda **kwargs: warnings.append(dict(kwargs))

            app._save_local_bank_transaction_categories_snapshot(FailingCategoryStore(), {})
            app._save_local_turnover_relations_snapshot(FailingRelationStore(), {})
            app._save_local_turnover_ledger_extras_snapshot(FailingExtraStore(), {})

        self.assertEqual(
            warnings,
            [
                {"operation": "bank_transaction_categories_updated", "detail": "category store unavailable"},
                {"operation": "turnover_relations_updated", "detail": "relation store unavailable"},
                {"operation": "turnover_ledger_extra_updated", "detail": "extra store unavailable"},
            ],
        )

    def test_postgres_turnover_ledger_persistence_repository_selects_postgres_only_for_execute_transactions(self) -> None:
        class ExecuteTransaction:
            def execute(self, *_args: object, **_kwargs: object) -> None:
                return None

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            state_store = object()

            postgres_repository = app._postgres_turnover_ledger_persistence_repository(
                ExecuteTransaction(),
                state_store=state_store,
            )
            fallback_repository = app._postgres_turnover_ledger_persistence_repository(
                object(),
                state_store=state_store,
            )

        self.assertIsInstance(postgres_repository, PostgresWorkbenchRepository)
        self.assertIs(fallback_repository, state_store)

    def test_turnover_ledger_tag_selection_primary_facade_updates_and_refreshes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            self._seed_turnover_tag_selection_settings(Path(temp_dir))
            app = build_application(data_dir=Path(temp_dir))
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)

            response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(
                    {
                        "expected_version": initial_payload["version"],
                        "selected_tag_codes": [],
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["selected_tag_codes"], [])
        self.assertGreater(payload["version"], initial_payload["version"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")])

    def test_turnover_ledger_tag_selection_legacy_fallback_facade_is_removed(self) -> None:
        self.assertFalse(hasattr(Application, "_turnover_ledger_tag_selection_legacy_fallback_facade"))

    def test_target_tag_selection_idempotency_key_replays_without_duplicate_settings_save_or_refresh(self) -> None:
        # PF-P183 target contract: same idempotency key/fingerprint should replay the first response.
        with TemporaryDirectory() as temp_dir:
            self._seed_turnover_tag_selection_settings(Path(temp_dir))
            app = build_application(data_dir=Path(temp_dir))
            queue = _PostgresQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)
            request_body = {
                "expected_version": initial_payload["version"],
                "selected_tag_codes": ["external_rule_repaid"],
                "idempotency_key": "tag-selection-idem-1",
            }

            first_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(request_body),
            )
            replay_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(request_body),
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(replay_response.status_code, 200)
        self.assertEqual(json.loads(replay_response.body), json.loads(first_response.body))
        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")],
        )
        self.assertEqual(read_repository.clear_calls, 0)

    def test_target_tag_selection_idempotency_key_conflict_rejects_different_payload(self) -> None:
        # PF-P183 target contract: same key with a different payload must fail before another settings save/refresh.
        with TemporaryDirectory() as temp_dir:
            self._seed_turnover_tag_selection_settings(Path(temp_dir))
            app = build_application(data_dir=Path(temp_dir))
            queue = _PostgresQueueRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            initial_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger/tag-selection").body)
            first_body = {
                "expected_version": initial_payload["version"],
                "selected_tag_codes": ["external_rule_repaid"],
                "idempotency_key": "tag-selection-idem-conflict",
            }
            conflict_body = {
                "expected_version": initial_payload["version"],
                "selected_tag_codes": ["external_rule_borrow_out"],
                "idempotency_key": "tag-selection-idem-conflict",
            }

            first_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(first_body),
            )
            conflict_response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/tag-selection",
                body=json.dumps(conflict_body),
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "idempotency_key_conflict")
        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [("turnover_ledger", "all", "turnover_ledger_tag_selection_changed")],
        )

    def test_turnover_bank_row_tag_batch_save_updates_category_and_reflects_to_bank_details(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )
            payload = json.loads(response.body)
            saved_category = app._bank_transaction_category_service.get(transaction_ids[0])
            app.shutdown_background_jobs()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["updated_categories"][0]["category_code"], "borrow_in_company_pending_repayment")
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertEqual(saved_category["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(saved_category["category_label"], "公司暂借款：待还款")

    def test_turnover_bank_row_tag_batch_queue_failure_happens_after_category_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _FailingQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/bank-row-tags/batch",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_ids[0],
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                )
            saved_category = app._bank_transaction_category_service.get(transaction_ids[0])

        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("bank_detail", "2026-02", "bank_transaction_category_changed"), queue.attempts)
        self.assertEqual(
            [item for item in queue.attempts if item[0] == "turnover_ledger"],
            [],
        )
        self.assertIsNone(saved_category["category_code"])

    def test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_category_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/bank-row-tags/batch",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_ids[0],
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                )
            saved_category = app._bank_transaction_category_service.get(transaction_ids[0])

        self.assertIsNone(saved_category["category_code"])
        self.assertIn(("bank_detail", "2026-02", "bank_transaction_category_changed"), queue.attempts)

    def test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_relation_snapshot(self) -> None:
        # PF-P118 characterization: local facade rollback must restore both category and relation snapshots.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            initial_category_snapshot = app._bank_transaction_category_service.snapshot()
            initial_relation_snapshot = app._turnover_relation_service.snapshot()
            saved_categories: list[dict[str, object]] = []
            saved_relations: list[dict[str, object]] = []
            original_save_categories = app._state_store.save_bank_transaction_categories
            original_save_relations = app._state_store.save_turnover_relations

            def record_save_categories(snapshot: dict[str, object]) -> None:
                saved_categories.append(dict(snapshot))
                original_save_categories(snapshot)

            def record_save_relations(snapshot: dict[str, object]) -> None:
                saved_relations.append(dict(snapshot))
                original_save_relations(snapshot)

            app._state_store.save_bank_transaction_categories = record_save_categories  # type: ignore[method-assign]
            app._state_store.save_turnover_relations = record_save_relations  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/bank-row-tags/batch",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_ids[0],
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                )

        self.assertEqual(app._bank_transaction_category_service.snapshot(), initial_category_snapshot)
        self.assertEqual(app._turnover_relation_service.snapshot(), initial_relation_snapshot)
        self.assertEqual(saved_categories[-1], initial_category_snapshot)
        self.assertEqual(saved_relations[-1], initial_relation_snapshot)

    def test_target_turnover_bank_row_tag_batch_local_facade_saves_snapshots_and_rebuilds_after_apply(self) -> None:
        # PF-P118 characterization: local facade success saves category/relation snapshots and preserves apply -> rebuild order.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            saved_categories: list[dict[str, object]] = []
            saved_relations: list[dict[str, object]] = []
            call_order: list[str] = []
            original_save_categories = app._state_store.save_bank_transaction_categories
            original_save_relations = app._state_store.save_turnover_relations
            original_apply = app._bank_transaction_category_service.apply_turnover_updates
            original_rebuild = app._turnover_relation_service.rebuild_from_bank_rows

            def record_save_categories(snapshot: dict[str, object]) -> None:
                saved_categories.append(dict(snapshot))
                original_save_categories(snapshot)

            def record_save_relations(snapshot: dict[str, object]) -> None:
                saved_relations.append(dict(snapshot))
                original_save_relations(snapshot)

            def record_apply(updates: list[dict[str, object]], *, actor: str) -> dict[str, object]:
                call_order.append("apply")
                return original_apply(updates, actor=actor)

            def record_rebuild(rows: list[dict[str, object]]) -> None:
                call_order.append("rebuild")
                original_rebuild(rows)

            app._state_store.save_bank_transaction_categories = record_save_categories  # type: ignore[method-assign]
            app._state_store.save_turnover_relations = record_save_relations  # type: ignore[method-assign]
            app._bank_transaction_category_service.apply_turnover_updates = record_apply  # type: ignore[method-assign]
            app._turnover_relation_service.rebuild_from_bank_rows = record_rebuild  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_order, ["apply", "rebuild"])
        self.assertGreaterEqual(len(saved_categories), 1)
        self.assertGreaterEqual(len(saved_relations), 1)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("bank_detail", "2026-02", "bank_transaction_category_changed"), queue.enqueued)
        self.assertIn(("workbench", "2026-02", "workbench_scope_invalidated"), queue.enqueued)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), queue.enqueued)

    def test_turnover_bank_row_tag_batch_facade_none_fails_fast_without_legacy_side_effects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            app._turnover_ledger_bank_row_tags_write_facade = lambda: None  # type: ignore[method-assign]
            saved_categories: list[dict[str, object]] = []
            call_order: list[str] = []
            original_save_categories = app._state_store.save_bank_transaction_categories
            original_rebuild = app._turnover_relation_service.rebuild_from_bank_rows

            def record_save_categories(snapshot: dict[str, object]) -> None:
                call_order.append("save_categories")
                saved_categories.append(dict(snapshot))
                original_save_categories(snapshot)

            def record_rebuild(rows: list[dict[str, object]]) -> None:
                call_order.append("rebuild")
                original_rebuild(rows)

            app._state_store.save_bank_transaction_categories = record_save_categories  # type: ignore[method-assign]
            app._turnover_relation_service.rebuild_from_bank_rows = record_rebuild  # type: ignore[method-assign]

            with self.assertRaisesRegex(RuntimeError, "turnover bank row tags write facade is unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/bank-row-tags/batch",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_ids[0],
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                )

        self.assertEqual(call_order, [])
        self.assertEqual(saved_categories, [])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.enqueued, [])

    def test_bank_row_tags_handler_override_passes_affected_months_and_keeps_response_flags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            facade = _BankRowTagsWriteFacadeRecorder()
            app._turnover_ledger_bank_row_tags_write_facade_override = facade

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            },
                            {
                                "transaction_id": transaction_ids[1],
                                "category_code": "borrow_in_company_repaid",
                                "expected_version": 0,
                            },
                        ]
                    }
                ),
            )
            payload = json.loads(response.body)
            app.shutdown_background_jobs()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["updated"], 2)
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-02", "2026-03"])
        self.assertEqual(payload["operation_barrier_targets"][0], {"read_model_key": "turnover_ledger", "scope_key": "2026-02"})
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertTrue(payload["workbench_invalidated"])
        self.assertEqual(
            facade.calls,
            [
                {
                    "updates": [
                        {
                            "transaction_id": transaction_ids[0],
                            "category_code": "borrow_in_company_pending_repayment",
                            "expected_version": 0,
                        },
                        {
                            "transaction_id": transaction_ids[1],
                            "category_code": "borrow_in_company_repaid",
                            "expected_version": 0,
                        },
                    ],
                    "actor_id": "test_finops_user",
                    "tenant_id": "default",
                    "affected_months": ["2026-02", "2026-03"],
                }
            ],
        )

    def test_confirm_relation_legacy_fallback_facade_is_removed(self) -> None:
        self.assertFalse(hasattr(Application, "_turnover_ledger_confirm_legacy_fallback_facade"))

    def test_turnover_bank_row_tag_batch_primary_facade_updates_and_refreshes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            saved_categories: list[dict[str, object]] = []
            call_order: list[str] = []
            original_save_categories = app._state_store.save_bank_transaction_categories
            original_rebuild = app._turnover_relation_service.rebuild_from_bank_rows

            def record_save_categories(snapshot: dict[str, object]) -> None:
                call_order.append("save_categories")
                saved_categories.append(dict(snapshot))
                original_save_categories(snapshot)

            def record_rebuild(rows: list[dict[str, object]]) -> None:
                call_order.append("rebuild")
                original_rebuild(rows)

            app._state_store.save_bank_transaction_categories = record_save_categories  # type: ignore[method-assign]
            app._turnover_relation_service.rebuild_from_bank_rows = record_rebuild  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(call_order), ["rebuild", "save_categories"])
        self.assertGreaterEqual(len(saved_categories), 1)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("bank_detail", "2026-02", "bank_transaction_category_changed"), queue.enqueued)
        self.assertIn(("workbench", "2026-02", "workbench_scope_invalidated"), queue.enqueued)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), queue.enqueued)

    def test_target_turnover_bank_row_tag_batch_handler_does_not_inline_legacy_fallback_side_effects(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_bank_row_tags_batch_route)

        self.assertNotIn("apply_turnover_updates(", source)
        self.assertNotIn("save_bank_transaction_categories(", source)
        self.assertNotIn("rebuild_from_bank_rows(", source)
        self.assertNotIn("_after_turnover_relation_mutation(", source)

    def test_bank_row_tags_handler_delegates_validation_affected_months_and_flags_to_request_facade(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_bank_row_tags_batch_route)

        self.assertIn("facade = self._bank_row_tags_request_boundary_provider()", source)
        self.assertIn("result = facade.update_bank_row_tags_batch_from_request(", source)
        self.assertNotIn("_ensure_turnover_bank_row_tag_targets(transaction_ids)", source)
        self.assertNotIn("affected_months = self._bank_transaction_category_affected_months(transaction_ids)", source)
        self.assertNotIn('result["affected_months"] = affected_months', source)
        self.assertNotIn('result["turnover_ledger_invalidated"] = True', source)
        self.assertNotIn('result["workbench_invalidated"] = True', source)

    def test_bank_row_tags_request_boundary_facade_wires_validation_and_affected_months_without_legacy_fallback(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_bank_row_tags_request_boundary_facade)

        self.assertIn("TurnoverLedgerBankRowTagsRequestBoundaryFacade(", source)
        self.assertIn("facade_provider=self._turnover_ledger_bank_row_tags_write_facade", source)
        self.assertNotIn("legacy_fallback_provider=", source)
        self.assertIn("target_validator=self._ensure_turnover_bank_row_tag_targets", source)
        self.assertIn("affected_months_resolver=self._bank_transaction_category_affected_months", source)

    def test_bank_row_tags_request_boundary_fails_fast_without_write_facade(self) -> None:
        facade = TurnoverLedgerBankRowTagsRequestBoundaryFacade(
            facade_provider=lambda: None,
            target_validator=lambda _transaction_ids: None,
            affected_months_resolver=lambda _transaction_ids: ["2026-02"],
        )

        with self.assertRaisesRegex(RuntimeError, "turnover bank row tags write facade is unavailable"):
            facade.update_bank_row_tags_batch_from_request(
                updates=[{"transaction_id": "bank-1", "category_code": "turnover"}],
                actor_id="user-1",
                tenant_id="default",
            )

    def test_turnover_bank_row_tags_write_facade_does_not_inline_local_snapshot_closures(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_bank_row_tags_write_facade)

        self.assertNotIn("save_category_snapshot=lambda", source)
        self.assertNotIn("save_relation_snapshot=lambda", source)

    def test_turnover_bank_row_tags_legacy_fallback_facade_is_removed(self) -> None:
        self.assertFalse(hasattr(Application, "_turnover_ledger_bank_row_tags_legacy_fallback_facade"))

    def test_turnover_relation_mutation_legacy_invalidation_path_is_removed(self) -> None:
        self.assertFalse(hasattr(Application, "_after_turnover_relation_mutation"))
        self.assertFalse(hasattr(Application, "_turnover_ledger_relation_mutation_invalidation_adapter"))
        self.assertFalse(hasattr(TurnoverLedgerReadModelRefreshProducer, "clear_best_effort"))

    def test_turnover_bank_row_tag_batch_postgres_facade_path_skips_legacy_after_mutation_helper(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _PostgresQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), [item[:3] for item in queue.transactional])
        self.assertEqual(queue.enqueued, [])

    def test_target_bank_row_tags_idempotency_key_replays_without_duplicate_category_update_relation_rebuild_or_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _PostgresQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            request_body = {
                "idempotency_key": "bank-row-tags-idem-1",
                "updates": [
                    {
                        "transaction_id": transaction_ids[0],
                        "category_code": "borrow_in_company_pending_repayment",
                        "expected_version": 0,
                    }
                ],
            }

            first_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(request_body),
            )
            replay_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(request_body),
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(replay_response.status_code, 200)
        self.assertEqual(json.loads(replay_response.body), json.loads(first_response.body))
        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [
                ("bank_detail", "2026-02", "bank_transaction_category_changed"),
                ("workbench", "2026-02", "workbench_scope_invalidated"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
            ],
        )
        self.assertEqual(read_repository.clear_calls, 0)

    def test_target_bank_row_tags_idempotency_key_conflict_rejects_different_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _PostgresQueueRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            first_body = {
                "idempotency_key": "bank-row-tags-idem-conflict",
                "updates": [
                    {
                        "transaction_id": transaction_ids[0],
                        "category_code": "borrow_in_company_pending_repayment",
                        "expected_version": 0,
                    }
                ],
            }
            conflict_body = {
                "idempotency_key": "bank-row-tags-idem-conflict",
                "updates": [
                    {
                        "transaction_id": transaction_ids[0],
                        "category_code": "borrow_out_company_lent",
                        "expected_version": 0,
                    }
                ],
            }

            first_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(first_body),
            )
            conflict_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(conflict_body),
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "idempotency_key_conflict")
        self.assertEqual(
            [item for item in queue.transactional if item[0] == "turnover_ledger"],
            [("turnover_ledger", "2026-02", "turnover_relation_changed", queue.transactional[-1][3])],
        )

    def test_turnover_bank_row_tag_batch_dependency_missing_fails_fast_without_side_effects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _FailingQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            with self.assertRaisesRegex(RuntimeError, "turnover bank row tags write facade is unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/bank-row-tags/batch",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_ids[0],
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                )
            category_snapshot = app._bank_transaction_category_service.snapshot()

        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.attempts, [])
        self.assertNotEqual(
            category_snapshot.get("categories", {}).get(transaction_ids[0], {}).get("category_code"),
            "borrow_in_company_pending_repayment",
        )

    def test_target_turnover_bank_row_tag_batch_uow_path_does_not_clear_read_model_directly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)

    def test_target_postgres_bank_row_tags_batch_uses_facade_without_direct_read_model_clear(self) -> None:
        # PF-P092 PostgreSQL Facade Readiness: postgres storage should enter facade/UoW path.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _PostgresQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), [item[:3] for item in queue.transactional])
        self.assertEqual(queue.enqueued, [])

    def test_turnover_bank_row_tag_batch_refreshes_all_required_scopes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(("bank_detail", "2026-02", "bank_transaction_category_changed"), queue.enqueued)
        self.assertIn(("workbench", "2026-02", "workbench_scope_invalidated"), queue.enqueued)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), queue.enqueued)

    def test_grouped_view_preserves_service_flow_rows_and_allocation_lots(self) -> None:
        class FakeLedgerService:
            def list_grouped_ledger(self, **_: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "family_summaries": [],
                    "filters": {"family": "company", "status": None},
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "groups": [
                        {
                            "group_id": "counterparty:company:梁希涛",
                            "counterparty_name": "梁希涛",
                            "family": "company",
                            "family_label": "公司往来",
                            "pending_direction": "repayment",
                            "pending_amount": "20000.00",
                            "summary_row": {
                                "relation_id": "turnover_rel_001",
                                "row_kind": "summary",
                                "borrow_amount": "200000.00",
                                "balance_amount": "20000.00",
                            },
                            "flow_rows": [
                                {
                                    "relation_id": "turnover_rel_001",
                                    "row_kind": "flow",
                                    "flow_id": "bank:bank_001",
                                    "source_bank_row_id": "bank_001",
                                    "flow_direction": "income",
                                    "flow_amount": "200000.00",
                                    "borrow_amount": "200000.00",
                                    "repayment_amount": "0.00",
                                },
                                {
                                    "relation_id": "turnover_rel_001",
                                    "row_kind": "flow",
                                    "flow_id": "bank:bank_002",
                                    "source_bank_row_id": "bank_002",
                                    "flow_direction": "expense",
                                    "flow_amount": "180000.00",
                                    "borrow_amount": "0.00",
                                    "repayment_amount": "180000.00",
                                },
                            ],
                            "allocation_lots": [
                                {
                                    "relation_id": "turnover_rel_001",
                                    "row_kind": "allocation_lot",
                                    "lot_id": "lot_001",
                                    "borrow_amount": "120000.00",
                                    "allocated_repayment_amount": "100000.00",
                                    "balance_amount": "20000.00",
                                }
                            ],
                            "lot_rows": [
                                {
                                    "relation_id": "turnover_rel_001",
                                    "row_kind": "lot",
                                    "lot_id": "lot_001",
                                    "borrow_amount": "120000.00",
                                    "balance_amount": "20000.00",
                                    "row_tone": "info",
                                }
                            ],
                            "row_span": 99,
                            "rows": [{"relation_id": "legacy"}],
                        }
                    ],
                }

        routes = TurnoverLedgerApiRoutes(
            ledger_service=FakeLedgerService(),  # type: ignore[arg-type]
            relation_service=object(),  # type: ignore[arg-type]
        )

        payload = routes.list_grouped_ledger(family="company")
        group = payload["groups"][0]

        self.assertEqual(group["row_span"], 3)
        self.assertEqual(group["summary_row"]["row_kind"], "summary")
        self.assertEqual(group["summary_row"]["display_level"], "group_summary")
        self.assertEqual([row["row_kind"] for row in group["flow_rows"]], ["flow", "flow"])
        self.assertEqual([row["source_bank_row_id"] for row in group["flow_rows"]], ["bank_001", "bank_002"])
        self.assertEqual(group["allocation_lots"][0]["row_kind"], "allocation_lot")
        self.assertEqual(group["lot_rows"][0]["row_kind"], "lot")
        self.assertEqual(group["lot_rows"][0]["lot_id"], "lot_001")
        self.assertEqual(group["lot_rows"][0]["balance_amount"], "20000.00")
        self.assertNotIn("rows", group)

    def test_grouped_view_converts_legacy_rows_to_summary_with_empty_flow_rows_and_lots(self) -> None:
        class FakeLegacyLedgerService:
            def list_grouped_ledger(self, **_: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "family_summaries": [],
                    "filters": {"family": "company", "status": None},
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "groups": [
                        {
                            "group_id": "counterparty:company:梁希涛",
                            "counterparty_name": "梁希涛",
                            "family": "company",
                            "family_label": "公司往来",
                            "pending_direction": "repayment",
                            "pending_amount": "20000.00",
                            "rows": [
                                {
                                    "relation_id": "turnover_rel_001",
                                    "borrow_amount": "200000.00",
                                    "balance_amount": "20000.00",
                                }
                            ],
                            "lot_rows": [
                                {
                                    "relation_id": "turnover_rel_001",
                                    "row_kind": "lot",
                                    "lot_id": "lot_legacy",
                                    "borrow_amount": "200000.00",
                                    "repayment_amount": "200000.00",
                                }
                            ],
                        }
                    ],
                }

        routes = TurnoverLedgerApiRoutes(
            ledger_service=FakeLegacyLedgerService(),  # type: ignore[arg-type]
            relation_service=object(),  # type: ignore[arg-type]
        )

        group = routes.list_grouped_ledger(family="company")["groups"][0]

        self.assertEqual(group["summary_row"]["relation_id"], "turnover_rel_001")
        self.assertEqual(group["summary_row"]["row_kind"], "summary")
        self.assertEqual(group["flow_rows"], [])
        self.assertEqual(group["allocation_lots"][0]["row_kind"], "allocation_lot")
        self.assertEqual(group["lot_rows"][0]["row_kind"], "lot")
        self.assertEqual(group["row_span"], 1)
        self.assertNotIn("rows", group)

    def test_grouped_view_preserves_flat_read_model_group_breakdowns(self) -> None:
        class FakeQueryService:
            def list_ledger(self, **_: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "family_summaries": [],
                    "filters": {"family": "personal", "status": None},
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "read_model_status": "fresh",
                    "rows": [
                        {
                            "relation_id": "turnover_rel_fang",
                            "family": "personal",
                            "family_label": "个人往来",
                            "counterparty_name": "房克丽",
                            "status": "suggested",
                            "row_tone": "warning",
                            "borrow_amount": "300000.00",
                            "repayment_amount": "100000.00",
                            "balance_amount": "200000.00",
                            "pending_repayment_amount": "200000.00",
                            "repaid_amount": "100000.00",
                            "pending_collection_amount": "50000.00",
                            "collected_amount": "25000.00",
                            "closed_amount": "0.00",
                        }
                    ],
                }

        routes = TurnoverLedgerApiRoutes(
            ledger_service=object(),  # type: ignore[arg-type]
            relation_service=object(),  # type: ignore[arg-type]
            query_service=FakeQueryService(),  # type: ignore[arg-type]
        )

        payload = routes.list_ledger(view="grouped", family="personal")
        group = payload["groups"][0]

        self.assertEqual(group["pending_direction"], "mixed")
        self.assertEqual(group["pending_direction_label"], "混合余额")
        self.assertEqual(group["pending_amount"], "250000.00")
        self.assertEqual(group["pending_repayment_amount"], "200000.00")
        self.assertEqual(group["pending_collection_amount"], "50000.00")
        self.assertEqual(group["repaid_amount"], "100000.00")
        self.assertEqual(group["collected_amount"], "25000.00")
        self.assertEqual(group["closed_amount"], "0.00")
        self.assertEqual(group["summary_row"]["pending_repayment_amount"], "200000.00")
        self.assertEqual(group["summary_row"]["pending_collection_amount"], "50000.00")
        # TODO: PF-P048 verify whether these backend-only compatibility fields can be removed safely.
        self.assertEqual(group["summary_row"]["repaid_amount"], "100000.00")
        self.assertEqual(group["summary_row"]["collected_amount"], "25000.00")

    def test_get_turnover_ledger_grouped_view_applies_family_filter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            self._import_and_tag_business_row(app)

            response = app.handle_request("GET", "/api/turnover-ledger?view=grouped&family=business")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["filters"]["family"], "business")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual([group["family"] for group in payload["groups"]], ["business"])
        self.assertEqual(payload["groups"][0]["counterparty_name"], "昆明建设集团")

    def test_relation_extra_get_returns_default_structure_and_put_persists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)
            relation_id = ledger_payload["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            get_response = app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra")
            put_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(
                    {
                        "interest_rate_type": "annual",
                        "interest_rate_value": "0.060000",
                        "interest_paid_amount": "120.50",
                        "interest_paid_date": "2026-04-01",
                        "interest_payment_method": "银行转账",
                        "note": "页面维护备注",
                    }
                ),
            )
            put_payload = json.loads(put_response.body)
            restored_response = app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra")
            restored_payload = json.loads(restored_response.body)
            reloaded_app = build_application(data_dir=Path(temp_dir), bootstrap_mode="legacy")
            reloaded_app._turnover_ledger_service._category_provider = None
            reloaded_response = reloaded_app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra")
            reloaded_payload = json.loads(reloaded_response.body)

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(json.loads(get_response.body)["extra"]["interest_rate_type"], "none")
        self.assertEqual(put_response.status_code, 200)
        self.assertEqual(put_payload["extra"]["interest_rate_value"], "0.060000")
        self.assertEqual(put_payload["extra"]["note"], "页面维护备注")
        self.assertEqual(put_payload["row"]["relation_id"], relation_id)
        self.assertEqual(restored_response.status_code, 200)
        self.assertEqual(restored_payload["extra"]["interest_paid_amount"], "120.50")
        self.assertEqual(reloaded_response.status_code, 200)
        self.assertEqual(reloaded_payload["extra"]["note"], "页面维护备注")
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("turnover_ledger", "all", "turnover_relation_extra_changed"), queue.enqueued)

    def test_relation_extra_same_payload_put_currently_updates_marker_and_reenqueues(self) -> None:
        # PF-P102 current behavior: repeated same payload is not durable-idempotent yet.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            payload = {"note": "same payload", "interest_rate_type": "none"}

            first_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(payload),
            )
            first_payload = json.loads(first_response.body)
            second_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(payload),
            )
            second_payload = json.loads(second_response.body)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_payload["extra"]["note"], "same payload")
        self.assertEqual(second_payload["extra"]["note"], "same payload")
        self.assertNotEqual(first_payload["extra"]["updated_at"], second_payload["extra"]["updated_at"])
        self.assertEqual(
            queue.enqueued,
            [
                ("turnover_ledger", "all", "turnover_relation_extra_changed"),
                ("turnover_ledger", "all", "turnover_relation_extra_changed"),
            ],
        )

    def test_target_relation_extra_idempotency_key_replays_without_duplicate_save_or_refresh(self) -> None:
        # PF-P105 target contract: same idempotency key/fingerprint should replay the first response.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            payload = {
                "note": "idempotent payload",
                "interest_rate_type": "none",
                "idempotency_key": "relation-extra-idem-1",
            }

            first_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(payload),
            )
            first_payload = json.loads(first_response.body)
            second_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(payload),
            )
            second_payload = json.loads(second_response.body)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_payload, first_payload)
        self.assertEqual(
            queue.enqueued,
            [("turnover_ledger", "all", "turnover_relation_extra_changed")],
        )

    def test_target_relation_extra_idempotency_key_conflict_rejects_different_payload(self) -> None:
        # PF-P105 target contract: same idempotency key with different payload must be a 409 conflict.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            first_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "first idem", "idempotency_key": "relation-extra-idem-conflict"}),
            )
            conflict_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "different idem", "idempotency_key": "relation-extra-idem-conflict"}),
            )
            restored_payload = json.loads(
                app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra").body
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "idempotency_key_conflict")
        self.assertEqual(restored_payload["extra"]["note"], "first idem")
        self.assertEqual(
            queue.enqueued,
            [("turnover_ledger", "all", "turnover_relation_extra_changed")],
        )

    def test_target_relation_extra_stale_expected_version_rejects_without_save_or_refresh(self) -> None:
        # PF-P102 target contract: stale relation extra writes should become conflict-safe.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            first_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "first version"}),
            )
            old_updated_at = json.loads(first_response.body)["extra"]["updated_at"]
            app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "newer version"}),
            )

            stale_response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps(
                    {
                        "note": "stale overwrite",
                        "expected_versions": {f"turnover_relation_extra:{relation_id}": old_updated_at},
                    }
                ),
            )
            restored_payload = json.loads(
                app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra").body
            )

        self.assertEqual(stale_response.status_code, 409)
        self.assertEqual(json.loads(stale_response.body)["error"], "turnover_relation_extra_conflict")
        self.assertEqual(restored_payload["extra"]["note"], "newer version")
        self.assertEqual(
            queue.enqueued,
            [
                ("turnover_ledger", "all", "turnover_relation_extra_changed"),
                ("turnover_ledger", "all", "turnover_relation_extra_changed"),
            ],
        )

    def test_relation_extra_persistence_failure_is_best_effort_success_and_refreshes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            def fail_save_turnover_ledger_extras(_snapshot: dict[str, object]) -> None:
                raise RuntimeError("extra store unavailable")

            app._state_store.save_turnover_ledger_extras = fail_save_turnover_ledger_extras  # type: ignore[method-assign]

            response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "persistence warning is best effort"}),
            )
            payload = json.loads(response.body)
            restored_response = app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra")
            restored_payload = json.loads(restored_response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extra"]["note"], "persistence warning is best effort")
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertEqual(restored_response.status_code, 200)
        self.assertEqual(restored_payload["extra"]["note"], "persistence warning is best effort")
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_relation_extra_changed")])

    def test_relation_extra_queue_failure_happens_after_extra_update_and_read_model_clear(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _FailingQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "PUT",
                    f"/api/turnover-ledger/relations/{relation_id}/extra",
                    body=json.dumps({"note": "queue failure happens after update"}),
                )
            restored_response = app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra")
            restored_payload = json.loads(restored_response.body)

        self.assertEqual(restored_response.status_code, 200)
        self.assertEqual(restored_payload["extra"]["note"], "")
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.attempts, [("turnover_ledger", "all", "turnover_relation_extra_changed")])

    def test_relation_extra_handler_does_not_inline_legacy_fallback_side_effects(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_relation_extra_update_route)

        self.assertNotIn("if facade is None", source)
        self.assertNotIn("_persist_turnover_ledger_extras_best_effort(", source)
        self.assertNotIn("_clear_turnover_ledger_read_model_best_effort(", source)
        self.assertNotIn("_enqueue_turnover_ledger_read_model_refreshes(", source)

    def test_relation_extra_handler_delegates_expected_versions_idempotency_and_stale_boundary(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_relation_extra_update_route)

        self.assertIn("facade = self._relation_extra_request_boundary_provider()", source)
        self.assertIn("result = facade.update_relation_extra_from_request(", source)
        self.assertIn("except TurnoverLedgerRelationExtraRequestBoundaryError as exc:", source)
        self.assertNotIn('expected_versions = payload.get("expected_versions")', source)
        self.assertNotIn(
            'idempotency_key = str(payload.get("idempotency_key") or payload.get("idempotencyKey") or "").strip() or None',
            source,
        )
        self.assertNotIn('expected_key = f"turnover_relation_extra:{relation_id}"', source)
        self.assertNotIn("self._turnover_ledger_read_facade.get_relation_extra(relation_id)", source)
        self.assertNotIn('"turnover_relation_extra_conflict"', source)

    def test_relation_extra_request_boundary_facade_wires_current_extra_reader_and_write_facade(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_relation_extra_request_boundary_facade)

        self.assertIn("TurnoverLedgerRelationExtraRequestBoundaryFacade(", source)
        self.assertIn("facade_provider=self._turnover_ledger_relation_extra_write_facade", source)
        self.assertIn("current_extra_reader=self._turnover_ledger_api_routes.get_relation_extra", source)

    def test_relation_extra_request_boundary_fails_fast_without_write_facade(self) -> None:
        facade = TurnoverLedgerRelationExtraRequestBoundaryFacade(
            facade_provider=lambda: None,
            current_extra_reader=lambda _relation_id: {"extra": {}},
        )

        with self.assertRaisesRegex(RuntimeError, "turnover relation extra write facade is unavailable"):
            facade.update_relation_extra_from_request(
                relation_id="rel-1",
                payload={"note": "no fallback"},
                actor_id="user-1",
                tenant_id="default",
                scope_keys=["all"],
            )

    def test_relation_extra_write_facade_does_not_inline_local_snapshot_closures(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_relation_extra_write_facade)

        self.assertNotIn("save_snapshot=lambda", source)

    def test_relation_extra_legacy_fallback_facade_is_removed(self) -> None:
        self.assertFalse(hasattr(Application, "_turnover_ledger_relation_extra_legacy_fallback_facade"))

    def test_target_relation_extra_queue_failure_rolls_back_extra_save(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            initial_payload = json.loads(
                app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra").body
            )
            queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "PUT",
                    f"/api/turnover-ledger/relations/{relation_id}/extra",
                    body=json.dumps({"note": "target rollback"}),
                )
            restored_payload = json.loads(
                app.handle_request("GET", f"/api/turnover-ledger/relations/{relation_id}/extra").body
            )

        self.assertEqual(restored_payload["extra"], initial_payload["extra"])
        self.assertEqual(queue.attempts, [("turnover_ledger", "all", "turnover_relation_extra_changed")])

    def test_target_relation_extra_uow_path_does_not_clear_read_model_directly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "target no clear"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extra"]["note"], "target no clear")
        self.assertEqual(payload["row"]["relation_id"], relation_id)
        self.assertEqual(queue.enqueued, [("turnover_ledger", "all", "turnover_relation_extra_changed")])
        self.assertEqual(read_repository.clear_calls, 0)

    def test_relation_extra_facade_override_skips_legacy_best_effort_side_effects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            facade = _RelationExtraWriteFacadeRecorder()
            app._turnover_ledger_relation_extra_write_facade_override = facade  # type: ignore[attr-defined]

            def unexpected_legacy_side_effect(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("legacy relation extra side effect should not run on facade path")

            app._persist_turnover_ledger_extras_best_effort = unexpected_legacy_side_effect  # type: ignore[method-assign]
            app._turnover_ledger_read_model_refresh_producer = unexpected_legacy_side_effect  # type: ignore[method-assign]

            response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/relations/turnover_rel_facade/extra",
                body=json.dumps({"note": "facade path"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extra"]["note"], "facade path")
        self.assertEqual(payload["row"], {"relation_id": "turnover_rel_facade", "note": "facade path"})
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertEqual(
            facade.calls,
            [
                {
                    "relation_id": "turnover_rel_facade",
                    "payload": {"note": "facade path"},
                    "actor_id": "test_finops_user",
                    "tenant_id": "default",
                    "scope_keys": ["all"],
                    "expected_versions": {},
                }
            ],
        )

    def test_relation_extra_handler_override_passes_expected_versions_and_idempotency_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            facade = _RelationExtraWriteFacadeRecorder()
            app._turnover_ledger_relation_extra_write_facade_override = facade  # type: ignore[attr-defined]

            response = app.handle_request(
                "PUT",
                "/api/turnover-ledger/relations/turnover_rel_facade/extra",
                body=json.dumps(
                    {
                        "note": "handler boundary",
                        "expected_versions": {"custom_scope": "v1"},
                        "idempotency_key": " idem-123 ",
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["extra"]["note"], "handler boundary")
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertEqual(
            facade.calls,
            [
                {
                    "relation_id": "turnover_rel_facade",
                    "payload": {
                        "note": "handler boundary",
                        "expected_versions": {"custom_scope": "v1"},
                        "idempotency_key": " idem-123 ",
                    },
                    "actor_id": "test_finops_user",
                    "tenant_id": "default",
                    "scope_keys": ["all"],
                    "expected_versions": {"custom_scope": "v1"},
                    "idempotency_key": "idem-123",
                }
            ],
        )

    def test_relation_extra_missing_dedicated_store_method_does_not_load_full_snapshot(self) -> None:
        class LegacyBootstrapRecorder:
            def __init__(self) -> None:
                self.reasons: list[str] = []

            def load_full_snapshot(self, *, reason: str) -> dict[str, object]:
                self.reasons.append(reason)
                return {"existing": "payload"}

        class LegacyStateStore:
            def __init__(self) -> None:
                self.saved_payload: dict[str, object] | None = None

            def save(self, payload: dict[str, object]) -> None:
                self.saved_payload = dict(payload)

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._turnover_ledger_api_routes.update_relation_extra = lambda *_args, **_kwargs: {}  # type: ignore[method-assign]
            app._turnover_ledger_api_routes._extra_service.upsert(  # type: ignore[attr-defined]
                "turnover_rel_legacy",
                {"note": "legacy fallback"},
                actor="tester",
            )
            legacy_bootstrap = LegacyBootstrapRecorder()
            legacy_store = LegacyStateStore()
            app._legacy_bootstrap = legacy_bootstrap  # type: ignore[assignment]
            app._state_store = legacy_store  # type: ignore[assignment]

            app._persist_turnover_ledger_extras_best_effort(operation="test_legacy_fallback")

        self.assertEqual(legacy_bootstrap.reasons, [])
        self.assertIsNone(legacy_store.saved_payload)

    def test_relation_extra_best_effort_uses_dedicated_store_without_full_snapshot_fallback(self) -> None:
        # PF-P110 characterization: dedicated extras persistence must not hit legacy full snapshot fallback.
        class DedicatedStateStore:
            def __init__(self) -> None:
                self.saved_extras: dict[str, object] | None = None

            def save_turnover_ledger_extras(self, snapshot: dict[str, object]) -> None:
                self.saved_extras = dict(snapshot)

        class FailingLegacyBootstrap:
            def load_full_snapshot(self, *, reason: str) -> dict[str, object]:
                raise AssertionError(f"legacy full snapshot fallback should not run: {reason}")

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._turnover_ledger_api_routes._extra_service.upsert(  # type: ignore[attr-defined]
                "turnover_rel_dedicated",
                {"note": "dedicated store"},
                actor="tester",
            )
            dedicated_store = DedicatedStateStore()
            app._state_store = dedicated_store  # type: ignore[assignment]
            app._legacy_bootstrap = FailingLegacyBootstrap()  # type: ignore[assignment]

            app._persist_turnover_ledger_extras_best_effort(operation="test_dedicated_store")

        self.assertIsNotNone(dedicated_store.saved_extras)
        extras = dedicated_store.saved_extras["extras"]  # type: ignore[index]
        self.assertEqual(extras[0]["relation_id"], "turnover_rel_dedicated")
        self.assertEqual(extras[0]["note"], "dedicated store")

    def test_relation_extra_put_rejects_invalid_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation_id = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)["rows"][0]["relation_id"]

            response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"interest_rate_type": "daily"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_turnover_ledger_extra")

    def test_relation_extra_put_rejects_readonly_user(self) -> None:
        with self._without_default_test_auth(), TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001", "FULL001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            identities = {
                "readonly-token": OAUserIdentity(
                    user_id="101",
                    username="READONLY001",
                    nickname="只读用户",
                    display_name="只读用户",
                    dept_id="01",
                    dept_name="财务部",
                    roles=["finance"],
                    permissions=[],
                ),
                "full-token": OAUserIdentity(
                    user_id="102",
                    username="FULL001",
                    nickname="操作用户",
                    display_name="操作用户",
                    dept_id="01",
                    dept_name="财务部",
                    roles=["finance"],
                    permissions=[],
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[str(token)]
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids, headers={"Authorization": "Bearer full-token"})
            relation_id = json.loads(
                app.handle_request(
                    "GET",
                    "/api/turnover-ledger",
                    headers={"Authorization": "Bearer full-token"},
                ).body
            )["rows"][0]["relation_id"]

            response = app.handle_request(
                "PUT",
                f"/api/turnover-ledger/relations/{relation_id}/extra",
                body=json.dumps({"note": "只读不允许保存"}),
                headers={"Authorization": "Bearer readonly-token"},
            )

        self.assertEqual(response.status_code, 403)

    def test_export_preview_uses_formal_fields_without_ui_only_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)

            response = app.handle_request("GET", "/api/turnover-ledger/export-preview?family=company")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["filters"]["family"], "company")
        self.assertIn("序号", payload["columns"])
        self.assertIn("往来大类", payload["columns"])
        self.assertGreaterEqual(len(payload["rows"]), 1)
        self.assertIn("row_type", payload["rows"][0])
        self.assertEqual(payload["rows"][0]["row_type"], "summary")
        flow_rows = [row for row in payload["rows"] if row.get("row_type") == "flow"]
        self.assertEqual(len(flow_rows), len({row["source_bank_row_id"] for row in flow_rows}))
        for row in flow_rows:
            self.assertIn(row["flow_direction"], {"income", "expense"})
            self.assertRegex(row["flow_amount"], r"^\d+\.\d{2}$")
        self.assertIn("lot_id", payload["rows"][0])
        self.assertIn("balance_amount", payload["rows"][0])
        forbidden_keys = {"chips", "row_tone", "group_tone", "row_span", "bank_row_ids"}
        self.assertFalse(forbidden_keys.intersection(payload["rows"][0]))

    def test_export_xlsx_returns_content_type_and_applies_family_filter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            self._import_and_tag_business_row(app)

            response = app.handle_request("GET", "/api/turnover-ledger/export?family=business")
            workbook = load_workbook(BytesIO(response.body))
            sheet = workbook.active
            header = [cell.value for cell in sheet[1]]
            data_row = [cell.value for cell in sheet[2]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("filename*=", response.headers["Content-Disposition"])
        self.assertIn("%E5%BE%80%E6%9D%A5%E6%AC%BE%E5%8F%B0%E8%B4%A6-", response.headers["Content-Disposition"])
        self.assertEqual(header[:7], ["序号", "行类型", "源银行流水ID", "流水方向", "流水金额", "往来大类", "对方户名"])
        self.assertIn("余额", header)
        self.assertEqual(data_row[1], "合计")
        self.assertEqual(data_row[5], "业务往来")
        self.assertEqual(data_row[6], "昆明建设集团")

    def test_export_limit_returns_structured_error(self) -> None:
        from fin_ops_platform.services.turnover_ledger_export_service import (
            TURNOVER_LEDGER_EXPORT_ROW_LIMIT,
            TurnoverLedgerExportLimitError,
        )

        class ExportLimitRoutes:
            @staticmethod
            def export_preview(**_kwargs: object) -> dict[str, object]:
                raise TurnoverLedgerExportLimitError(total=TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1)

            @staticmethod
            def export(**_kwargs: object) -> tuple[str, bytes]:
                raise TurnoverLedgerExportLimitError(total=TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1)

        app = build_application()
        app._turnover_ledger_api_routes.export_preview = ExportLimitRoutes.export_preview  # type: ignore[method-assign]
        app._turnover_ledger_api_routes.export = ExportLimitRoutes.export  # type: ignore[method-assign]

        preview_response = app.handle_request("GET", "/api/turnover-ledger/export-preview?family=all")
        export_response = app.handle_request("GET", "/api/turnover-ledger/export?family=all")

        expected_details = {"total": TURNOVER_LEDGER_EXPORT_ROW_LIMIT + 1, "limit": TURNOVER_LEDGER_EXPORT_ROW_LIMIT}
        preview_payload = json.loads(preview_response.body)
        export_payload = json.loads(export_response.body)
        self.assertEqual(preview_response.status_code, 400)
        self.assertEqual(export_response.status_code, 400)
        self.assertEqual(preview_payload["error"], "turnover_ledger_export_row_limit_exceeded")
        self.assertEqual(export_payload["error"], "turnover_ledger_export_row_limit_exceeded")
        self.assertEqual(preview_payload["details"], expected_details)
        self.assertEqual(export_payload["details"], expected_details)

    def test_confirm_and_withdraw_require_mutation_permission_and_write_audit(self) -> None:
        with self._without_default_test_auth(), TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001", "FULL001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            identities = {
                "readonly-token": OAUserIdentity(
                    user_id="101",
                    username="READONLY001",
                    nickname="只读用户",
                    display_name="只读用户",
                    dept_id="01",
                    dept_name="财务部",
                    roles=["finance"],
                    permissions=[],
                ),
                "full-token": OAUserIdentity(
                    user_id="102",
                    username="FULL001",
                    nickname="操作用户",
                    display_name="操作用户",
                    dept_id="01",
                    dept_name="财务部",
                    roles=["finance"],
                    permissions=[],
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[str(token)]
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids, headers={"Authorization": "Bearer full-token"})
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            denied = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids}),
                headers={"Authorization": "Bearer readonly-token"},
            )
            confirmed = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "人工确认部分还款关系"}),
                headers={"Authorization": "Bearer full-token"},
            )
            confirmed_payload = json.loads(confirmed.body)
            relation_id = confirmed_payload["relation"]["relation_id"]
            withdrawn = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "撤回测试"}),
                headers={"Authorization": "Bearer full-token"},
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(withdrawn.status_code, 200)
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation", "withdraw_relation"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_confirm_duplicate_submit_rejects_after_first_success_without_second_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            first_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "first confirm"}),
            )
            duplicate_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "duplicate confirm"}),
            )
            duplicate_payload = json.loads(duplicate_response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(duplicate_response.status_code, 400)
        self.assertEqual(duplicate_payload["error"], "relation_row_conflict")
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_confirm_relation_persistence_failure_is_best_effort_success_and_still_enqueues_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            def fail_save_turnover_relations(_snapshot: dict[str, object]) -> None:
                raise RuntimeError("relation store unavailable")

            app._state_store.save_turnover_relations = fail_save_turnover_relations  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "persistence failure"}),
            )
            payload = json.loads(response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["relation"]["status"], "confirmed")
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_confirm_relation_handler_does_not_inline_legacy_fallback_side_effects(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_confirm_relation_route)

        self.assertNotIn("if facade is not None", source)
        self.assertNotIn("rebuild_from_bank_rows(", source)
        self.assertNotIn("_after_turnover_relation_mutation(", source)

    def test_confirm_handler_delegates_affected_months_boundary_to_request_facade(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_confirm_relation_route)

        self.assertIn("facade = self._confirm_relation_request_boundary_provider()", source)
        self.assertIn("result = facade.confirm_relation_from_request(", source)
        self.assertNotIn("normalized_bank_row_ids = [str(row_id) for row_id in bank_row_ids]", source)
        self.assertNotIn("affected_months = self._bank_transaction_category_affected_months(normalized_bank_row_ids)", source)
        self.assertNotIn('result["affected_months"] = affected_months', source)

    def test_closure_confirm_handler_delegates_affected_months_boundary_to_request_facade(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_closure_confirm_route)

        self.assertIn("facade = self._closure_request_boundary_provider()", source)
        self.assertIn("result = facade.confirm_zero_difference_closure_from_request(", source)
        self.assertNotIn("rebuild_from_bank_rows(", source)
        self.assertNotIn("_after_turnover_relation_mutation(", source)
        self.assertNotIn("_resolve_turnover_relation_affected_months", source)

    def test_closure_withdraw_handler_uses_closure_boundary_without_relation_withdraw_inline(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_closure_withdraw_route)

        self.assertIn("facade = self._closure_request_boundary_provider()", source)
        self.assertIn("result = facade.withdraw_cash_closure_case_from_request(", source)
        self.assertIn('payload.get("cash_closure_case_id") or payload.get("cashClosureCaseId")', source)
        self.assertNotIn("withdraw_relation_from_request(", source)
        self.assertNotIn("_after_turnover_relation_mutation(", source)

    def test_confirm_request_boundary_facade_owns_affected_months_resolution_and_response_field(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_confirm_request_boundary_facade)

        self.assertIn("TurnoverLedgerConfirmRequestBoundaryFacade(", source)
        self.assertIn("affected_months_resolver=self._turnover_bank_transaction_affected_months", source)
        self.assertIn("cash_closure_relation_provider=self._turnover_cash_closure_relation", source)

    def test_turnover_affected_months_uses_one_bulk_fact_read(self) -> None:
        source = inspect.getsource(Application._turnover_bank_transaction_affected_months)

        self.assertIn("list_transactions_by_ids(transaction_ids)", source)
        self.assertNotIn("get_transaction(", source)

    def test_confirm_and_closure_request_boundaries_fail_fast_without_write_facade(self) -> None:
        facade = TurnoverLedgerConfirmRequestBoundaryFacade(
            facade=None,
            affected_months_resolver=lambda _bank_row_ids: ["2026-02"],
        )

        with self.assertRaisesRegex(RuntimeError, "turnover confirm write facade is unavailable"):
            facade.confirm_relation_from_request(
                bank_row_ids=["bank-1"],
                actor_id="user-1",
                tenant_id="default",
                note=None,
            )
        with self.assertRaisesRegex(RuntimeError, "turnover closure write facade is unavailable"):
            facade.confirm_zero_difference_closure_from_request(
                bank_row_ids=["bank-1", "bank-2"],
                actor_id="user-1",
                tenant_id="default",
                note=None,
            )
        with self.assertRaisesRegex(RuntimeError, "turnover cash closure withdraw facade is unavailable"):
            facade.withdraw_cash_closure_case_from_request(
                cash_closure_case_id="case-1",
                actor_id="user-1",
                tenant_id="default",
                note=None,
            )

    def test_confirm_relation_write_facade_does_not_inline_local_snapshot_or_rebuild_closures(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_confirm_write_facade)

        self.assertNotIn("save_snapshot=lambda", source)
        self.assertNotIn("relation_rebuild=lambda", source)

    def test_confirm_relation_queue_failure_happens_after_relation_confirm_and_read_model_clear(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _FailingQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/relations/confirm",
                    body=json.dumps({"bank_row_ids": transaction_ids, "note": "queue failure after confirm"}),
                )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual([entry["action"] for entry in audit_log], [])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.attempts if item[0] == "turnover_ledger"],
            [("turnover_ledger", "2026-02", "turnover_relation_changed")],
        )

    def test_target_confirm_relation_queue_failure_rolls_back_relation_confirm(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    "/api/turnover-ledger/relations/confirm",
                    body=json.dumps({"bank_row_ids": transaction_ids, "note": "target rollback"}),
                )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(audit_log, [])
        self.assertEqual(
            [item for item in queue.attempts if item[0] == "turnover_ledger"],
            [("turnover_ledger", "2026-02", "turnover_relation_changed")],
        )

    def test_confirm_relation_primary_facade_rebuilds_confirms_and_invalidates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            call_order: list[str] = []
            original_rebuild = app._turnover_relation_service.rebuild_from_bank_rows

            def record_rebuild(rows: list[dict[str, object]]) -> None:
                call_order.append("rebuild")
                original_rebuild(rows)

            app._turnover_relation_service.rebuild_from_bank_rows = record_rebuild  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "primary confirm"}),
            )
            payload = json.loads(response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["relation"]["status"], "confirmed")
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-02", "2026-03"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [
                {"read_model_key": "turnover_ledger", "scope_key": "2026-02"},
                {"read_model_key": "turnover_ledger", "scope_key": "2026-03"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-02"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-03"},
            ],
        )
        self.assertEqual(call_order, ["rebuild"])
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), queue.enqueued)
        self.assertIn(("turnover_ledger", "2026-03", "turnover_relation_changed"), queue.enqueued)

    def test_target_confirm_relation_uow_path_does_not_clear_read_model_directly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "target no clear"}),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)

    def test_target_postgres_confirm_relation_uses_facade_without_direct_read_model_clear(self) -> None:
        # PF-P092 PostgreSQL Facade Readiness: confirm relation should not fall back on postgres.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            turnover_rows = app._turnover_bank_transaction_rows()
            queue = _PostgresQueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._state_store = _PostgresLikeStateStore(app._state_store)  # type: ignore[assignment]
            app._turnover_bank_transaction_rows_by_ids = lambda row_ids: [  # type: ignore[method-assign]
                dict(row)
                for row in turnover_rows
                if str(row.get("id") or "") in set(row_ids)
            ]
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "postgres facade readiness"}),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )
        self.assertEqual(queue.enqueued, [])

    def test_confirm_relation_facade_override_skips_legacy_after_mutation_side_effects(self) -> None:
        # PF-P110 characterization: facade path must not call handler fallback invalidation orchestration.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            facade = _RelationWriteFacadeRecorder()
            app._turnover_ledger_confirm_write_facade_override = facade

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "facade confirm"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["relation"]["relation_id"], "turnover_rel_facade_confirm")
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(
            facade.confirm_calls,
            [
                {
                    "bank_row_ids": transaction_ids,
                    "actor_id": "test_finops_user",
                    "tenant_id": "default",
                    "note": "facade confirm",
                    "affected_months": ["2026-02", "2026-03"],
                    "expected_versions": {},
                }
            ],
        )

    def test_withdraw_duplicate_submit_rejects_after_first_withdraw_without_second_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "first confirm"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]

            first_withdraw_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "first withdraw"}),
            )
            second_withdraw_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "duplicate withdraw"}),
            )
            second_payload = json.loads(second_withdraw_response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(confirmed_response.status_code, 200)
        self.assertEqual(first_withdraw_response.status_code, 200)
        self.assertEqual(second_withdraw_response.status_code, 409)
        self.assertEqual(second_payload["error"], "relation_already_withdrawn")
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [
                ("confirm_relation", "confirmed"),
                ("withdraw_relation", "withdrawn"),
            ],
        )
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_target_withdraw_idempotency_key_replays_without_duplicate_withdraw_or_refresh(self) -> None:
        # PF-P179 target contract: same idempotency key/fingerprint should replay the first withdraw response.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before idempotent withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            request_body = {"note": "idempotent withdraw", "idempotency_key": "withdraw-idem-1"}

            first_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps(request_body),
            )
            second_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps(request_body),
            )
            first_payload = json.loads(first_response.body)
            second_payload = json.loads(second_response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_payload, first_payload)
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [
                ("confirm_relation", "confirmed"),
                ("withdraw_relation", "withdrawn"),
            ],
        )
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_target_withdraw_idempotency_key_conflict_rejects_different_payload(self) -> None:
        # PF-P179 target contract: same idempotency key with different payload must be a 409 conflict.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before idempotent withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]

            first_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "first withdraw", "idempotency_key": "withdraw-idem-conflict"}),
            )
            conflict_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "different withdraw", "idempotency_key": "withdraw-idem-conflict"}),
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(conflict_response.status_code, 409)
        self.assertEqual(json.loads(conflict_response.body)["error"], "idempotency_key_conflict")
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [
                ("confirm_relation", "confirmed"),
                ("withdraw_relation", "withdrawn"),
            ],
        )
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_target_withdraw_duplicate_submit_rejects_without_second_mutation_or_refresh(self) -> None:
        # PF-P099 target contract: duplicate withdraw should become a conflict, not a second mutation.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "first confirm"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]

            first_withdraw_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "first withdraw"}),
            )
            second_withdraw_response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "duplicate withdraw"}),
            )
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(confirmed_response.status_code, 200)
        self.assertEqual(first_withdraw_response.status_code, 200)
        self.assertIn(second_withdraw_response.status_code, {400, 409})
        self.assertEqual(
            [(entry["action"], entry["new_status"]) for entry in audit_log],
            [
                ("confirm_relation", "confirmed"),
                ("withdraw_relation", "withdrawn"),
            ],
        )
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear(self) -> None:
        # PF-P092 PostgreSQL Facade Readiness: withdraw relation should not fall back on postgres.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": _PostgresQueueRecorder()})()
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before postgres withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            read_repository = _TurnoverReadModelRecorder()
            queue = _PostgresQueueRecorder()
            app._state_store = _PostgresLikeStateStore(  # type: ignore[assignment]
                app._state_store,
                app._workbench_pair_relation_service,
            )
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "postgres facade readiness"}),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item[:3] for item in queue.transactional],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("workbench", "2026-02", "turnover_relation_changed"),
                ("workbench", "2026-03", "turnover_relation_changed"),
                ("workbench_relation", "2026-02", "turnover_relation_changed"),
                ("workbench_relation", "2026-03", "turnover_relation_changed"),
                ("cost_statistics", "active:2026-02", "cost_statistics_relation_delta"),
                ("cost_statistics", "active:2026-03", "cost_statistics_relation_delta"),
                ("search", "2026-02", "turnover_relation_changed"),
                ("search", "2026-03", "turnover_relation_changed"),
            ],
        )
        self.assertEqual(queue.enqueued, [])

    def test_withdraw_relation_facade_override_skips_legacy_after_mutation_side_effects(self) -> None:
        # PF-P110 characterization: facade path must not call direct fallback invalidation orchestration.
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            try:
                transaction_ids = self._import_bank_rows(app)
                self._tag_rows(app, transaction_ids)
                confirmed_response = app.handle_request(
                    "POST",
                    "/api/turnover-ledger/relations/confirm",
                    body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before facade withdraw"}),
                )
                relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
                facade = _RelationWriteFacadeRecorder()
                app._turnover_ledger_withdraw_write_facade_override = facade

                response = app.handle_request(
                    "POST",
                    f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                    body=json.dumps({"note": "facade withdraw"}),
                )
                payload = json.loads(response.body)
            finally:
                app.shutdown_background_jobs()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["relation"]["relation_id"], relation_id)
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-02", "2026-03"])
        self.assertEqual(payload["freshness_targets"][0], {"read_model_key": "turnover_ledger", "scope_key": "2026-02"})
        self.assertEqual(len(facade.withdraw_calls), 1)
        self.assertEqual(facade.withdraw_calls[0]["relation_id"], relation_id)
        self.assertEqual(facade.withdraw_calls[0]["note"], "facade withdraw")
        self.assertEqual(facade.withdraw_calls[0]["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(facade.withdraw_calls[0]["expected_versions"], {f"relation:{relation_id}": 1})

    def test_withdraw_relation_handler_does_not_inline_legacy_fallback_side_effects(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_withdraw_relation_route)

        self.assertNotIn("if facade is not None", source)
        self.assertNotIn("self._turnover_ledger_api_routes.withdraw_relation", source)
        self.assertNotIn("_after_turnover_relation_mutation(", source)

    def test_withdraw_handler_delegates_precheck_expected_versions_and_affected_months_to_request_facade(self) -> None:
        source = inspect.getsource(TurnoverLedgerApiRoutes.handle_withdraw_relation_route)

        self.assertIn("facade = self._withdraw_request_boundary_provider()", source)
        self.assertIn("result = facade.withdraw_relation_from_request(", source)
        self.assertIn("except TurnoverLedgerWithdrawRequestBoundaryError as exc:", source)
        self.assertNotIn("detail = self._turnover_ledger_api_routes.get_relation(relation_id)", source)
        self.assertNotIn('if str(relation.get("source") or "") != "manual":', source)
        self.assertNotIn('if str(relation.get("status") or "") == "withdrawn":', source)
        self.assertNotIn('expected_versions[f"relation:{relation_id}"] = int(relation.get("version") or 0)', source)
        self.assertNotIn('result["affected_months"] = affected_months', source)

    def test_withdraw_request_boundary_facade_wires_relation_detail_and_affected_months_resolver(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_withdraw_request_boundary_facade)

        self.assertIn("TurnoverLedgerWithdrawRequestBoundaryFacade(", source)
        self.assertIn("relation_detail_provider=self._turnover_ledger_api_routes.get_relation", source)
        self.assertIn("affected_months_resolver=self._turnover_bank_transaction_affected_months", source)

    def test_withdraw_request_boundary_fails_fast_without_write_facade(self) -> None:
        facade = TurnoverLedgerWithdrawRequestBoundaryFacade(
            facade=None,
            relation_detail_provider=lambda _relation_id: {
                "relation": {
                    "source": "manual",
                    "status": "active",
                    "bank_row_ids": ["bank-1"],
                    "version": 1,
                }
            },
            affected_months_resolver=lambda _bank_row_ids: ["2026-02"],
        )

        with self.assertRaisesRegex(RuntimeError, "turnover withdraw write facade is unavailable"):
            facade.withdraw_relation_from_request(
                relation_id="rel-1",
                actor_id="user-1",
                tenant_id="default",
                note=None,
            )

    def test_withdraw_relation_write_facade_does_not_inline_local_snapshot_closures(self) -> None:
        source = inspect.getsource(Application._turnover_ledger_withdraw_write_facade)

        self.assertNotIn("save_snapshot=lambda", source)

    def test_withdraw_relation_queue_failure_happens_after_relation_withdraw_and_read_model_clear(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            failing_queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": failing_queue})()

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                    body=json.dumps({"note": "queue failure after withdraw"}),
                )
            audit_log = app._turnover_relation_service.audit_log()
            relation_detail = app._turnover_ledger_api_routes.get_relation(relation_id)

        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation"])
        self.assertEqual(relation_detail["relation"]["status"], "confirmed")
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in failing_queue.attempts if item[0] == "turnover_ledger"],
            [("turnover_ledger", "2026-02", "turnover_relation_changed")],
        )

    def test_withdraw_relation_primary_facade_withdraws_and_invalidates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before primary withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            queue.enqueued.clear()
            read_repository.clear_calls = 0

            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "primary withdraw"}),
            )
            payload = json.loads(response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["relation"]["relation_id"], relation_id)
        self.assertEqual(payload["relation"]["status"], "withdrawn")
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(payload["operation_barrier_targets"][2], {"read_model_key": "workbench_relation", "scope_key": "2026-02"})
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation", "withdraw_relation"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertIn(("turnover_ledger", "2026-02", "turnover_relation_changed"), queue.enqueued)
        self.assertIn(("turnover_ledger", "2026-03", "turnover_relation_changed"), queue.enqueued)
        self.assertIn(("workbench_relation", "2026-02", "turnover_relation_changed"), queue.enqueued)

    def test_target_withdraw_relation_queue_failure_rolls_back_relation_withdraw(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before target withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]
            failing_queue = _FailingQueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": failing_queue})()

            with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
                app.handle_request(
                    "POST",
                    f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                    body=json.dumps({"note": "target rollback"}),
                )
            audit_log = app._turnover_relation_service.audit_log()
            relation_detail = app._turnover_ledger_api_routes.get_relation(relation_id)

        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation"])
        self.assertEqual(relation_detail["relation"]["status"], "confirmed")
        self.assertEqual(
            [item for item in failing_queue.attempts if item[0] == "turnover_ledger"],
            [("turnover_ledger", "2026-02", "turnover_relation_changed")],
        )

    def test_target_withdraw_relation_uow_path_does_not_clear_read_model_directly(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository
            confirmed_response = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "confirm before no-clear withdraw"}),
            )
            relation_id = json.loads(confirmed_response.body)["relation"]["relation_id"]

            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "target no clear"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["affected_months"], ["2026-02", "2026-03"])
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(
            [item for item in queue.enqueued if item[0] == "turnover_ledger"],
            [
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
                ("turnover_ledger", "2026-02", "turnover_relation_changed"),
                ("turnover_ledger", "2026-03", "turnover_relation_changed"),
            ],
        )

    def test_withdraw_rejects_system_generated_relation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)
            relation_id = ledger_payload["rows"][0]["relation_id"]
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "不能撤回系统关系"}),
            )
            payload = json.loads(response.body)
            audit_log = app._turnover_relation_service.audit_log()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "system_relation_cannot_withdraw")
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(audit_log, [])

    def test_turnover_bank_row_tag_batch_rejects_non_turnover_rows_without_refresh_side_effects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="non-turnover-bank.xlsx",
                imported_by="YNSYLP005",
                rows=[
                    {
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司基本户",
                        "txn_date": "2026-02-04",
                        "trade_time": "2026-02-04 13:23:17",
                        "pay_receive_time": "2026-02-04 13:23:17",
                        "counterparty_name": "银行",
                        "debit_amount": "10.00",
                        "credit_amount": "",
                        "summary": "账户管理费",
                        "remark": "手续费",
                        "imported_bank_name": "建行",
                        "imported_bank_last4": "8106",
                    }
                ],
            )
            app._import_service.confirm_import(preview.id)
            transaction_id = app._import_service.list_transactions()[0].id
            queue = _QueueRecorder()
            read_repository = _TurnoverReadModelRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            app._workbench_sql_read_repository = read_repository
            app._turnover_ledger_sql_read_repository = read_repository

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/bank-row-tags/batch",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_id,
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "not_turnover_bank_row")
        self.assertEqual(payload["transaction_id"], transaction_id)
        self.assertEqual(read_repository.clear_calls, 0)
        self.assertEqual(queue.enqueued, [])

    def test_disabled_category_save_leaves_turnover_relations_unchanged(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            relation = app._turnover_relation_service.confirm_relation(
                transaction_ids,
                actor="YNSYLP005",
                note="seed manual relation",
            )
            app._state_store.save_turnover_relations(app._turnover_relation_service.snapshot())

            response = app.handle_request(
                "PATCH",
                "/api/bank-details/transactions/categories",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_ids[0],
                                "category_code": "borrow_out_company_lent",
                                "expected_version": 1,
                            }
                        ]
                    }
                ),
            )
            payload = json.loads(response.body)
            restored_relation = next(
                item
                for item in app._state_store.load_turnover_relations()["relations"]
                if item["relation_id"] == relation["relation_id"]
            )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(payload["error"], "manual_bank_transaction_category_disabled")
        self.assertEqual(restored_relation["status"], relation["status"])
        self.assertEqual(restored_relation.get("sync_to_workbench"), relation.get("sync_to_workbench"))

    def test_state_store_round_trips_turnover_relations_locally(self) -> None:
        snapshot = {
            "schema_version": "test",
            "relations": [{"relation_id": "turnover_rel_1", "status": "suggested"}],
            "audit_log": [{"relation_id": "turnover_rel_1", "action": "seed"}],
        }
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))

            store.save_turnover_relations(snapshot)
            restored = store.load_turnover_relations()
            audit_log = store.load_turnover_relation_audit_log()

        self.assertEqual(restored, snapshot)
        self.assertEqual(audit_log, snapshot["audit_log"])


if __name__ == "__main__":
    unittest.main()
