from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application, StatePersistenceError, build_application
from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import (
    CallbackWorkbenchRelationRepository,
    WorkbenchRelationCommandService,
)


class FakeBatchRelationFacade:
    def __init__(self, relation: dict[str, object] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._relation = relation

    def list_by_month(self, month: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"month": month, **kwargs})
        if month != "2026-01":
            return {"status": "fresh", "rows": [], "groups": [], "source_versions": {}, "read_model_scope_keys": [month]}
        return self._payload()

    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        self.calls.append({"row_ids": list(row_ids), **kwargs})
        payload = self._payload()
        payload["rows"] = [
            row
            for row in list(payload["rows"])
            if str(row.get("row_id") or "") in {str(row_id) for row_id in row_ids}
        ]
        return payload

    def _payload(self) -> dict[str, object]:
        if isinstance(self._relation, dict):
            metadata = self._relation.get("special_metadata") if isinstance(self._relation.get("special_metadata"), dict) else {}
            row_ids = [str(row_id) for row_id in list(self._relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(self._relation.get("row_types") or [])]
            group_id = str(self._relation.get("case_id") or "")
            bank_row_id = str(metadata.get("bank_row_id") or row_ids[0] if row_ids else "")
            linked_oa = [{"id": row_id} for index, row_id in enumerate(row_ids) if index < len(row_types) and row_types[index] == "oa"]
            linked_invoices = [{"id": row_id} for index, row_id in enumerate(row_ids) if index < len(row_types) and row_types[index] == "invoice"]
            return {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": bank_row_id,
                        "row_type": "bank_transaction",
                        "group_ids": [group_id],
                        "linked_oa": linked_oa,
                        "linked_bank_transactions": [{"id": bank_row_id}],
                        "linked_input_invoices": linked_invoices,
                        "linked_output_invoices": [],
                    }
                ],
                "groups": [
                    {
                        "group_id": group_id,
                        "payload": {
                            "group_id": group_id,
                            "relation_mode": str(self._relation.get("relation_mode") or "manual_confirmed"),
                            "special_metadata": dict(metadata),
                            "row_ids": row_ids,
                            "row_types": row_types,
                            "note": str(self._relation.get("note") or ""),
                            "amount_check": dict(self._relation.get("amount_check") or {}) if isinstance(self._relation.get("amount_check"), dict) else {},
                        },
                    }
                ],
                "source_versions": {"schema_version": 52},
                "read_model_scope_keys": ["2026-01"],
                "refresh_enqueued": False,
                "stale_reasons": [],
            }
        return {
            "status": "fresh",
            "rows": [
                {
                    "row_id": "txn_imported_202601_batch_001",
                    "row_type": "bank_transaction",
                    "group_ids": ["CASE-BATCH-txn_imported_202601_batch_001"],
                    "linked_oa": [
                        {"id": "oa-exp-ba-001", "applicant": "刘晨", "project_name": "品牌广告投放"},
                        {"id": "oa-exp-ba-002", "applicant": "王明", "project_name": "品牌广告投放"},
                    ],
                    "linked_bank_transactions": [
                        {"id": "txn_imported_202601_batch_001", "amount": "1200.00", "direction": "outflow"}
                    ],
                    "linked_input_invoices": [
                        {"id": "oa-att-inv-oa-exp-ba-001-01", "total_with_tax": "700.00"},
                        {"id": "oa-att-inv-oa-exp-ba-002-01", "total_with_tax": "500.00"},
                    ],
                    "linked_output_invoices": [],
                }
            ],
            "groups": [
                {
                    "group_id": "CASE-BATCH-txn_imported_202601_batch_001",
                    "payload": {
                        "group_id": "CASE-BATCH-txn_imported_202601_batch_001",
                        "relation_mode": "manual_confirmed",
                        "special_metadata": {
                            "source": "batch_accounting",
                            "bank_row_id": "txn_imported_202601_batch_001",
                            "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                            "invoice_row_ids": ["oa-att-inv-oa-exp-ba-001-01", "oa-att-inv-oa-exp-ba-002-01"],
                            "year": "2026",
                        },
                        "row_ids": [
                            "txn_imported_202601_batch_001",
                            "oa-exp-ba-001",
                            "oa-exp-ba-002",
                            "oa-att-inv-oa-exp-ba-001-01",
                            "oa-att-inv-oa-exp-ba-002-01",
                        ],
                        "row_types": ["bank", "oa", "oa", "invoice", "invoice"],
                    },
                }
            ],
            "source_versions": {"schema_version": 52},
            "read_model_scope_keys": ["2026-01"],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }


class NonFreshBatchRelationFacade(FakeBatchRelationFacade):
    def __init__(
        self,
        *,
        status: str,
        stale_reasons: list[str],
        read_model_scope_keys: list[str] | None = None,
        refresh_enqueued: bool | None = True,
    ) -> None:
        super().__init__(None)
        self._status = status
        self._stale_reasons = stale_reasons
        self._read_model_scope_keys = read_model_scope_keys or ["2026-01"]
        self._refresh_enqueued = refresh_enqueued

    def list_by_month(self, month: str, **kwargs: object) -> dict[str, object]:
        payload = super().list_by_month(month, **kwargs)
        if self._refresh_enqueued is None:
            payload["refresh_enqueued"] = bool(kwargs.get("require_fresh"))
        return payload

    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        payload = super().get_by_row_ids(row_ids, **kwargs)
        if self._refresh_enqueued is None:
            payload["refresh_enqueued"] = bool(kwargs.get("require_fresh"))
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "status": self._status,
            "rows": [],
            "groups": [],
            "source_versions": {},
            "read_model_scope_keys": list(self._read_model_scope_keys),
            "refresh_enqueued": bool(self._refresh_enqueued),
            "stale_reasons": list(self._stale_reasons),
        }


class WriteBlockingPairRelationService(WorkbenchPairRelationService):
    def replace_with_confirmed_relation(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BatchAccountingService must delegate submit relation writes to WorkbenchRelationCommandService.")

    def withdraw_latest_for_row_ids(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BatchAccountingService must delegate withdraw relation writes to WorkbenchRelationCommandService.")


class RepairWriteBlockingPairRelationService(WorkbenchPairRelationService):
    def create_active_relation(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BatchAccountingService must delegate repair relation writes to WorkbenchRelationCommandService.")

    def record_history(self, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("BatchAccountingService must delegate repair relation history to WorkbenchRelationCommandService.")


class RecordingBatchRelationCommandService:
    def __init__(self, pair_relation_service: WorkbenchPairRelationService | None = None) -> None:
        self._pair_relation_service = pair_relation_service
        self.confirm_calls: list[dict[str, object]] = []
        self.withdraw_calls: list[dict[str, object]] = []

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        if self._pair_relation_service is None:
            return []
        return self._pair_relation_service.active_relations_for_row_ids(row_ids)

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        if self._pair_relation_service is None:
            return None
        return self._pair_relation_service.get_active_relation_by_case_id(case_id)

    def list_active_relations(self) -> list[dict[str, object]]:
        if self._pair_relation_service is None:
            return []
        return self._pair_relation_service.list_active_relations()

    def list_history(self) -> list[dict[str, object]]:
        if self._pair_relation_service is None:
            return []
        return self._pair_relation_service.list_history()

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": str(kwargs["case_id"]),
            "row_ids": list(kwargs["row_ids"]),
            "row_types": list(kwargs["row_types"]),
            "status": "active",
            "relation_mode": str(kwargs["relation_mode"]),
            "month_scope": str(kwargs["month_scope"]),
            "created_by": str(kwargs["actor_id"]),
            "note": str(kwargs.get("note") or ""),
            "amount_check": dict(kwargs.get("amount_check") or {}),
            "special_metadata": dict(kwargs.get("special_metadata") or {}),
            "version": 1,
        }
        return {
            "status": "confirmed",
            "relation": relation,
            "history": {"operation_type": str(kwargs.get("history_operation_type") or "confirm_link")},
            "changed_case_ids": [relation["case_id"]],
            "affected_months": ["2026-01"],
            "version": 1,
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-01"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }

    def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.withdraw_calls.append(dict(kwargs))
        return {
            "status": "withdrawn",
            "relation": {
                "case_id": str(kwargs["case_id"]),
                "row_ids": ["txn_imported_202601_batch_001", "oa-exp-ba-001"],
                "status": "cancelled",
                "month_scope": "2026-01",
                "version": 2,
            },
            "history": {"operation_type": "withdraw_link"},
            "restored_relations": [],
            "changed_case_ids": [str(kwargs["case_id"])],
            "affected_row_ids": ["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            "affected_months": ["2026-01"],
            "version": 2,
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-01"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }


def relation_command_service_for(pair_relation_service: WorkbenchPairRelationService) -> WorkbenchRelationCommandService:
    def save_snapshot(snapshot: dict[str, object], *, changed_case_ids: list[str]) -> None:
        changed_ids = {str(case_id).strip() for case_id in list(changed_case_ids or []) if str(case_id).strip()}
        current = pair_relation_service.snapshot()
        current_relations = dict(current.get("pair_relations") if isinstance(current.get("pair_relations"), dict) else {})
        incoming_relations = dict(snapshot.get("pair_relations") if isinstance(snapshot.get("pair_relations"), dict) else {})
        for case_id in changed_ids:
            if case_id in incoming_relations:
                current_relations[case_id] = incoming_relations[case_id]
            else:
                current_relations.pop(case_id, None)
        restored = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": current_relations,
                "pair_relation_history": list(snapshot.get("pair_relation_history") or []),
            }
        )
        pair_relation_service._pair_relations = restored._pair_relations
        pair_relation_service._pair_relation_history = restored._pair_relation_history

    return WorkbenchRelationCommandService(
        relation_repository=CallbackWorkbenchRelationRepository(
            load_snapshot=pair_relation_service.snapshot,
            save_snapshot=save_snapshot,
        ),
        relation_facade=FakeBatchRelationFacade(),
    )


class BatchAccountingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def _grouped_payload(self) -> dict[str, object]:
        eligible_bank = {
            "id": "txn_imported_202601_batch_001",
            "type": "bank",
            "trade_time": "2026-01-07 15:54:00",
            "pay_receive_time": "2026-01-07 15:54:00",
            "counterparty_name": " 批量账务集中处理 ",
            "debit_amount": "1200.00",
            "credit_amount": "",
            "payment_account_label": "建行基本户 8106",
            "bank_name": "建行",
            "account_last4": "8106",
            "version": 1,
        }
        return {
            "month": "all",
            "summary": {},
            "paired": {"groups": []},
            "open": {
                "groups": [
                    {
                        "group_id": "eligible-bank",
                        "bank_rows": [eligible_bank],
                        "oa_rows": [],
                        "invoice_rows": [],
                    },
                    {
                        "group_id": "wrong-counterparty-bank",
                        "bank_rows": [
                            {
                                **eligible_bank,
                                "id": "txn_imported_202601_other_counterparty",
                                "counterparty_name": "批量账务集中处理-代付",
                            }
                        ],
                        "oa_rows": [],
                        "invoice_rows": [],
                    },
                    {
                        "group_id": "income-bank",
                        "bank_rows": [
                            {
                                **eligible_bank,
                                "id": "txn_imported_202601_income",
                                "debit_amount": "",
                                "credit_amount": "1200.00",
                            }
                        ],
                        "oa_rows": [],
                        "invoice_rows": [],
                    },
                    {
                        "group_id": "wrong-year-bank",
                        "bank_rows": [
                            {
                                **eligible_bank,
                                "id": "txn_imported_202501_batch_001",
                                "trade_time": "2025-12-31 10:00:00",
                                "pay_receive_time": "2025-12-31 10:00:00",
                            }
                        ],
                        "oa_rows": [],
                        "invoice_rows": [],
                    },
                    {
                        "group_id": "case:CASE-OA-INVOICE",
                        "group_type": "candidate",
                        "oa_rows": [
                            {
                                "id": "oa-exp-ba-001",
                                "type": "oa",
                                "case_id": "CASE-OA-INVOICE",
                                "applicant": "刘晨",
                                "apply_time": "2026-01-06",
                                "project_name": "品牌广告投放",
                                "amount": "700.00",
                                "reason": "1月日常报销",
                                "apply_type": "日常报销",
                                "expense_type": "交通费",
                                "summary_fields": {"申请日期": "2026-01-06"},
                            }
                        ],
                        "bank_rows": [],
                        "invoice_rows": [
                            {
                                "id": "oa-att-inv-oa-exp-ba-001-01",
                                "type": "invoice",
                                "case_id": "CASE-OA-INVOICE",
                                "source_kind": "oa_attachment_invoice",
                                "derived_from_oa_id": "oa-exp-ba-001",
                                "total_with_tax": "700.00",
                            }
                        ],
                    },
                    {
                        "group_id": "case:CASE-OA-ONLY",
                        "oa_rows": [
                            {
                                "id": "oa-exp-ba-002",
                                "type": "oa",
                                "case_id": "CASE-OA-ONLY",
                                "applicant": "王明",
                                "apply_time": "2026-01-07",
                                "project_name": "市场活动项目",
                                "amount": "500.00",
                                "reason": "1月活动报销",
                                "apply_type": "差旅日常报销",
                                "expense_type": "差旅费",
                                "summary_fields": {"申请日期": "2026-01-07"},
                            },
                            {
                                "id": "oa-exp-ba-003",
                                "type": "oa",
                                "case_id": "CASE-OA-ONLY",
                                "applicant": "赵敏",
                                "project_name": "办公用品",
                                "amount": "300.00",
                                "reason": "日常办公用品报销",
                                "apply_type": "日常报销",
                                "expense_type": "办公费",
                                "detail_fields": {"申请日期": "2026-01-08"},
                            },
                            {
                                "id": "oa-pay-001",
                                "type": "oa",
                                "applicant": "供应商",
                                "apply_time": "2026-01-07",
                                "amount": "500.00",
                                "apply_type": "付款申请",
                                "expense_type": "服务费",
                                "summary_fields": {"申请日期": "2026-01-07"},
                            },
                            {
                                "id": "oa-exp-ba-2025",
                                "type": "oa",
                                "applicant": "旧年",
                                "apply_time": "2025-12-31",
                                "amount": "500.00",
                                "apply_type": "日常报销",
                                "expense_type": "差旅费",
                                "summary_fields": {"申请日期": "2025-12-31"},
                            },
                            {
                                "id": "oa-exp-ba-2025b",
                                "type": "oa",
                                "applicant": "旧年补充",
                                "apply_time": "2025-12-30",
                                "amount": "700.00",
                                "apply_type": "日常报销",
                                "expense_type": "交通费",
                                "summary_fields": {"申请日期": "2025-12-30"},
                            },
                        ],
                        "bank_rows": [],
                        "invoice_rows": [],
                    },
                ]
            },
        }

    def _large_batch_accounting_payload(self, total: int = 250) -> dict[str, object]:
        bank_rows = [
            {
                "id": f"txn_imported_202601_batch_{index:03d}",
                "type": "bank",
                "trade_time": f"2026-01-{(index % 28) + 1:02d} 09:00:00",
                "pay_receive_time": f"2026-01-{(index % 28) + 1:02d} 09:00:00",
                "counterparty_name": " 批量账务集中处理 ",
                "debit_amount": "10.00",
                "credit_amount": "",
                "payment_account_label": f"建行基本户 {index:04d}",
                "bank_name": "建行",
                "account_last4": f"{index % 10000:04d}",
                "version": 1,
            }
            for index in range(total)
        ]
        oa_rows = [
            {
                "id": f"oa-exp-ba-{index:03d}",
                "type": "oa",
                "case_id": f"CASE-OA-{index:03d}",
                "applicant": f"申请人{index:03d}",
                "apply_time": f"2026-01-{(index % 28) + 1:02d}",
                "project_name": "批量账务首屏保护",
                "amount": "10.00",
                "reason": "日常报销",
                "apply_type": "日常报销",
                "expense_type": "交通费",
                "summary_fields": {"申请日期": f"2026-01-{(index % 28) + 1:02d}"},
            }
            for index in range(total)
        ]
        return {
            "month": "all",
            "summary": {},
            "paired": {"groups": []},
            "open": {
                "groups": [
                    {
                        "group_id": "large-batch-bank",
                        "bank_rows": bank_rows,
                        "oa_rows": [],
                        "invoice_rows": [],
                    },
                    {
                        "group_id": "large-batch-oa",
                        "bank_rows": [],
                        "oa_rows": oa_rows,
                        "invoice_rows": [],
                    },
                ]
            },
        }

    def _app_with_grouped_payload(self) -> tuple[Application, patch]:
        app = build_application()
        payload_patcher = patch.object(app, "_build_api_workbench_payload", return_value=self._grouped_payload())
        payload_patcher.start()
        self.addCleanup(payload_patcher.stop)
        return app, payload_patcher

    def test_unsubmitted_list_uses_sql_read_model_loader_when_available(self) -> None:
        class SqlReadModel:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload
                self.calls: list[tuple[str, str]] = []

            def load_batch_accounting_workbench_payload(self, *, bank_year: str, oa_year: str) -> dict[str, object]:
                self.calls.append((bank_year, oa_year))
                return self.payload

        app = build_application()
        sql_read_model = SqlReadModel(self._grouped_payload())
        app._workbench_sql_read_repository = sql_read_model
        payload_patcher = patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("full workbench loader must not run"))
        payload_patcher.start()
        self.addCleanup(payload_patcher.stop)

        response = app.handle_request("GET", "/api/batch-accounting?bank_year=2026&oa_year=2025&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(sql_read_model.calls, [("2026", "2025")])
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])
        self.assertEqual([row["id"] for row in payload["oa_rows"]], ["oa-exp-ba-2025", "oa-exp-ba-2025b"])

    def test_unsubmitted_list_explicit_pagination_protects_first_screen_slo(self) -> None:
        app = build_application()
        payload_patcher = patch.object(app, "_build_api_workbench_payload", return_value=self._large_batch_accounting_payload())
        payload_patcher.start()
        self.addCleanup(payload_patcher.stop)

        first_response = app.handle_request(
            "GET",
            "/api/batch-accounting?year=2026&bucket=unsubmitted&page=1&page_size=200",
        )
        second_response = app.handle_request(
            "GET",
            "/api/batch-accounting?year=2026&bucket=unsubmitted&page=2&page_size=200",
        )
        invalid_response = app.handle_request(
            "GET",
            "/api/batch-accounting?year=2026&bucket=unsubmitted&page=1&page_size=201",
        )
        first_payload = json.loads(first_response.body)
        second_payload = json.loads(second_response.body)
        invalid_payload = json.loads(invalid_response.body)

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(len(first_payload["bank_rows"]), 200)
        self.assertEqual(len(first_payload["oa_rows"]), 200)
        self.assertEqual(first_payload["summary"]["unsubmitted_count"], 250)
        self.assertEqual(
            first_payload["pagination"],
            {
                "bank_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 250},
                "oa_rows": {"page": 1, "page_size": 200, "pageSize": 200, "total": 250},
            },
        )
        self.assertEqual(second_response.status_code, 200, second_response.body)
        self.assertEqual(len(second_payload["bank_rows"]), 50)
        self.assertEqual(len(second_payload["oa_rows"]), 50)
        self.assertEqual(second_payload["summary"]["unsubmitted_count"], 250)
        self.assertEqual(
            second_payload["pagination"],
            {
                "bank_rows": {"page": 2, "page_size": 200, "pageSize": 200, "total": 250},
                "oa_rows": {"page": 2, "page_size": 200, "pageSize": 200, "total": 250},
            },
        )
        self.assertEqual(invalid_response.status_code, 400, invalid_response.body)
        self.assertEqual(invalid_payload["error"], "invalid_paging")
        self.assertEqual(invalid_payload["message"], "page_size must be <= 200.")

    def test_unsubmitted_list_deduplicates_sql_read_model_rows_by_row_id(self) -> None:
        duplicate_payload = self._grouped_payload()
        group = duplicate_payload["open"]["groups"][0]
        group["bank_rows"] = [group["bank_rows"][0], {**group["bank_rows"][0], "version": 2}]
        group["oa_rows"] = [
            {
                "id": "oa-exp-ba-001",
                "type": "oa",
                "applicant": "刘晨",
                "apply_time": "2026-01-06",
                "amount": "700.00",
                "apply_type": "日常报销",
            },
            {
                "id": "oa-exp-ba-001",
                "type": "oa",
                "applicant": "刘晨",
                "apply_time": "2026-01-06",
                "amount": "700.00",
                "apply_type": "日常报销",
            },
        ]

        class SqlReadModel:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def load_batch_accounting_workbench_payload(self, *, bank_year: str, oa_year: str) -> dict[str, object]:
                self.calls.append((bank_year, oa_year))
                return duplicate_payload

        app = build_application()
        sql_read_model = SqlReadModel()
        app._workbench_sql_read_repository = sql_read_model
        payload_patcher = patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("SQL loader should be used"))
        payload_patcher.start()
        self.addCleanup(payload_patcher.stop)

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(sql_read_model.calls, [("2026", "2026")])
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])
        self.assertEqual([row["id"] for row in payload["oa_rows"]], ["oa-exp-ba-001", "oa-exp-ba-002", "oa-exp-ba-003"])

    def test_unsubmitted_list_does_not_run_legacy_relation_repair(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        self.assertFalse(hasattr(app, "_repair_batch_accounting_relation_case_ids"))

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])

    def _submit_batch_mismatch_with_note(self, app: Application, *, note: str) -> dict[str, object]:
        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001"],
                    "note": note,
                    "actor": "finance-user",
                }
            ),
        )
        self.assertEqual(response.status_code, 200, response.body)
        return json.loads(response.body)

    def test_unsubmitted_list_filters_bank_rows_and_daily_reimbursement_oa_rows(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])
        self.assertEqual(payload["bank_rows"][0]["counterparty_name"], "批量账务集中处理")
        self.assertEqual(payload["bank_rows"][0]["direction"], "expense")
        self.assertEqual(payload["bank_rows"][0]["amount"], "1200.00")
        self.assertEqual([row["id"] for row in payload["oa_rows"]], ["oa-exp-ba-001", "oa-exp-ba-002", "oa-exp-ba-003"])
        self.assertEqual(payload["oa_rows"][0]["linked_invoice_row_ids"], ["oa-att-inv-oa-exp-ba-001-01"])
        self.assertEqual(payload["oa_rows"][2]["apply_time"], "2026-01-08")
        self.assertEqual(payload["summary"]["unsubmitted_count"], 1)
        self.assertEqual(payload["summary"]["submitted_count"], 0)

    def test_unsubmitted_list_uses_independent_bank_and_oa_years(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "GET",
            "/api/batch-accounting?bank_year=2026&oa_year=2025&bucket=unsubmitted",
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])
        self.assertEqual([row["id"] for row in payload["oa_rows"]], ["oa-exp-ba-2025", "oa-exp-ba-2025b"])
        self.assertEqual(payload["summary"]["bank_year"], "2026")
        self.assertEqual(payload["summary"]["oa_year"], "2025")

    def test_unsubmitted_list_excludes_bank_rows_already_linked_elsewhere(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        relation = {
            "case_id": "CASE-OTHER-LINK",
            "row_ids": ["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            "row_types": ["bank", "oa"],
            "relation_mode": "manual_confirmed",
            "special_metadata": {"bank_row_id": "txn_imported_202601_batch_001"},
        }
        app._workbench_relation_facade = FakeBatchRelationFacade(relation)

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["bank_rows"], [])
        self.assertEqual(payload["summary"]["unsubmitted_count"], 0)

    def test_unsubmitted_list_exposes_relation_read_model_missing_status(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        app._workbench_relation_facade = NonFreshBatchRelationFacade(
            status="missing",
            stale_reasons=["read_model_missing"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=True,
        )

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["read_model_status"], "missing")
        self.assertEqual(payload["read_model_stale_reasons"], ["read_model_missing"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-01"])
        self.assertIs(payload["refresh_enqueued"], True)

    def test_unsubmitted_list_requires_fresh_relation_read_model_to_enqueue_missing_refresh(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        facade = NonFreshBatchRelationFacade(
            status="missing",
            stale_reasons=["read_model_missing"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=None,
        )
        app._workbench_relation_facade = facade

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["read_model_status"], "missing")
        self.assertIs(payload["refresh_enqueued"], True)
        self.assertTrue(
            any(call.get("row_ids") and call.get("require_fresh") is True for call in facade.calls),
            facade.calls,
        )

    def test_submitted_list_requires_fresh_relation_read_model_to_enqueue_stale_refresh(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        facade = NonFreshBatchRelationFacade(
            status="stale",
            stale_reasons=["dirty_scope:2026-01"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=None,
        )
        app._workbench_relation_facade = facade

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=submitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertIs(payload["refresh_enqueued"], True)
        self.assertTrue(
            any(call.get("month") == "2026-01" and call.get("require_fresh") is True for call in facade.calls),
            facade.calls,
        )

    def test_submit_amount_mismatch_requires_difference_note(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001"],
                    "amount": "1200.00",
                    "invoice_row_ids": [],
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(payload["error"], "batch_accounting_note_required")
        self.assertEqual(payload["amount_check"]["status"], "mismatch")
        self.assertEqual(payload["amount_check"]["direction"], "expense")
        self.assertEqual(payload["amount_check"]["bank_amount"], "1200.00")
        self.assertEqual(payload["amount_check"]["oa_amount"], "700.00")
        self.assertEqual(payload["amount_check"]["amount_delta"], "500.00")
        self.assertTrue(payload["amount_check"]["requires_note"])
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001"))

    def test_submit_amount_mismatch_rejects_whitespace_note(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001"],
                    "note": "   ",
                }
            ),
        )

        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(json.loads(response.body)["error"], "batch_accounting_note_required")

    def test_submit_amount_mismatch_with_note_persists_relation_and_history(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        payload = self._submit_batch_mismatch_with_note(app, note="OA合计不含员工餐补扣款，财务确认闭环")

        relation = payload["pair_relation"]
        self.assertEqual(relation["note"], "OA合计不含员工餐补扣款，财务确认闭环")
        self.assertEqual(relation["amount_check"]["status"], "mismatch")
        self.assertEqual(relation["amount_check"]["direction"], "expense")
        self.assertEqual(relation["amount_check"]["bank_amount"], "1200.00")
        self.assertEqual(relation["amount_check"]["oa_amount"], "700.00")
        self.assertEqual(relation["amount_check"]["amount_delta"], "500.00")
        self.assertTrue(relation["amount_check"]["requires_note"])
        self.assertEqual(relation["special_metadata"]["source"], "batch_accounting")
        history = app._workbench_pair_relation_service.list_history()[-1]
        self.assertEqual(history["note"], "OA合计不含员工餐补扣款，财务确认闭环")
        self.assertEqual(history["amount_check"]["status"], "mismatch")

    def test_submit_delegates_relation_write_to_command_service(self) -> None:
        pair_service = WriteBlockingPairRelationService()
        relation_command = RecordingBatchRelationCommandService(pair_service)
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: self._grouped_payload(),
            relation_facade=FakeBatchRelationFacade(),
            relation_command_service=relation_command,
        )

        result = service.submit(
            year="2026",
            bank_row_id="txn_imported_202601_batch_001",
            oa_row_ids=["oa-exp-ba-001", "oa-exp-ba-002"],
            actor="finance-user",
        )

        self.assertEqual(result["relation_id"], "CASE-BATCH-txn_imported_202601_batch_001")
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertEqual(call["relation_mode"], "batch_accounting")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["history_operation_type"], "confirm_link")
        self.assertIs(call["replace_existing"], True)
        self.assertEqual(result["pair_relation"]["relation_mode"], "batch_accounting")

    def test_submit_requires_relation_command_service_without_direct_pair_fallback(self) -> None:
        pair_service = WriteBlockingPairRelationService()
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: self._grouped_payload(),
            relation_facade=FakeBatchRelationFacade(),
        )

        with self.assertRaises(BatchAccountingError) as context:
            service.submit(
                year="2026",
                bank_row_id="txn_imported_202601_batch_001",
                oa_row_ids=["oa-exp-ba-001", "oa-exp-ba-002"],
                actor="finance-user",
            )

        self.assertEqual(context.exception.code, "batch_accounting_relation_command_unavailable")

    def test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        previous_snapshot = app._workbench_pair_relation_service.snapshot()

        def fail_persist(*_args, **_kwargs):
            raise StatePersistenceError("persist failed")

        app._schedule_workbench_pair_relation_persist = fail_persist
        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001"],
                    "note": "财务确认差额闭环",
                }
            ),
        )

        self.assertEqual(response.status_code, 503, response.body)
        self.assertEqual(json.loads(response.body)["error"], "workbench_state_persistence_unavailable")
        self.assertEqual(app._workbench_pair_relation_service.snapshot(), previous_snapshot)

    def test_submit_creates_batch_accounting_relation_with_current_invoice_rows(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "invoice_row_ids": [],
                    "actor": "finance-user",
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["relation_id"], "CASE-BATCH-txn_imported_202601_batch_001")
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(payload["relation_id"])
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "batch_accounting")
        self.assertCountEqual(
            relation["row_ids"],
            [
                "txn_imported_202601_batch_001",
                "oa-exp-ba-001",
                "oa-exp-ba-002",
                "oa-att-inv-oa-exp-ba-001-01",
            ],
        )
        self.assertEqual(
            relation["special_metadata"],
            {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_202601_batch_001",
                "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                "invoice_row_ids": ["oa-att-inv-oa-exp-ba-001-01"],
                "year": "2026",
                "bank_year": "2026",
                "oa_year": "2026",
                "oa_years": ["2026"],
                "created_by": "finance-user",
            },
        )
        self.assertEqual(payload["affected_months"], ["2026-01", "all"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-01", "all"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [
                {"read_model_key": "workbench_relation", "scope_key": "2026-01"},
                {"read_model_key": "workbench_relation", "scope_key": "all"},
            ],
        )

    def test_submit_rejects_when_relation_read_model_is_not_fresh(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        app._workbench_relation_facade = NonFreshBatchRelationFacade(
            status="missing",
            stale_reasons=["read_model_missing"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=True,
        )

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "actor": "finance-user",
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(payload["error"], "batch_accounting_read_model_not_fresh")
        self.assertEqual(payload["read_model_status"], "missing")
        self.assertEqual(payload["read_model_stale_reasons"], ["read_model_missing"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-01"])
        self.assertIs(payload["refresh_enqueued"], True)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001"))

    def test_submit_matched_amount_ignores_supplied_difference_note(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "note": "上一次选择留下的差额说明",
                    "actor": "finance-user",
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(payload["relation_id"])
        assert relation is not None
        self.assertEqual(relation["amount_check"]["status"], "matched")
        self.assertEqual(relation["note"], "日常报销批量账务管理提交")
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["note"], "日常报销批量账务管理提交")

    def test_submit_uses_bank_row_scoped_relation_id_without_consuming_auto_override_ids(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "actor": "finance-user",
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["relation_id"], "CASE-BATCH-txn_imported_202601_batch_001")
        self.assertEqual(app._workbench_override_service._next_case_id(), "CASE-AUTO-0001")

    def test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service(self) -> None:
        lost_relation = {
            "case_id": "CASE-AUTO-0002",
            "row_ids": ["txn_imported_1263", "oa-exp-1981"],
            "row_types": ["bank", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "created_by": "local_finops_admin",
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1263",
                "oa_row_ids": ["oa-exp-1981"],
            },
        }
        pair_service = RepairWriteBlockingPairRelationService(
            pair_relation_history=[
                {
                    "operation_type": "confirm_link",
                    "before_relations": [],
                    "after_relations": [lost_relation],
                    "affected_row_ids": list(lost_relation["row_ids"]),
                    "created_by": "local_finops_admin",
                }
            ]
        )
        relation_command = RecordingBatchRelationCommandService(pair_service)
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
            relation_command_service=relation_command,
        )

        result = service.repair_legacy_case_id_collisions(actor="repair-user")

        self.assertTrue(result["changed"])
        self.assertEqual(result["changed_case_ids"], ["CASE-BATCH-txn_imported_1263"])
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertEqual(call["case_id"], "CASE-BATCH-txn_imported_1263")
        self.assertEqual(call["history_operation_type"], "repair_batch_accounting_relation_id_collision")
        self.assertEqual(call["actor_id"], "repair-user")
        self.assertEqual(call["special_metadata"]["legacy_case_id"], "CASE-AUTO-0002")
        self.assertEqual(call["special_metadata"]["repair_source"], "batch_accounting_case_id_collision")

    def test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback(self) -> None:
        lost_relation = {
            "case_id": "CASE-AUTO-0002",
            "row_ids": ["txn_imported_1263", "oa-exp-1981"],
            "row_types": ["bank", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "created_by": "local_finops_admin",
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1263",
                "oa_row_ids": ["oa-exp-1981"],
            },
        }
        pair_service = RepairWriteBlockingPairRelationService(
            pair_relation_history=[
                {
                    "operation_type": "confirm_link",
                    "before_relations": [],
                    "after_relations": [lost_relation],
                    "affected_row_ids": list(lost_relation["row_ids"]),
                    "created_by": "local_finops_admin",
                }
            ]
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
        )

        with self.assertRaises(BatchAccountingError) as context:
            service.repair_legacy_case_id_collisions()

        self.assertEqual(context.exception.code, "batch_accounting_relation_command_unavailable")

    def test_repair_legacy_case_id_collision_restores_lost_batch_relation_from_history(self) -> None:
        pair_service = WorkbenchPairRelationService()
        lost_relation = {
            "case_id": "CASE-AUTO-0002",
            "row_ids": ["txn_imported_1263", "oa-exp-1981", "oa-exp-1984"],
            "row_types": ["bank", "oa", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "created_by": "local_finops_admin",
            "created_at": "2026-05-19T02:58:05+00:00",
            "updated_at": "2026-05-19T02:58:05+00:00",
            "amount_check": {"status": "matched", "bank_amount": "429.31", "oa_amount": "429.31"},
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1263",
                "oa_row_ids": ["oa-exp-1981", "oa-exp-1984"],
                "year": "2026",
            },
        }
        later_relation = {
            **lost_relation,
            "row_ids": ["txn_imported_1234", "oa-exp-1962"],
            "row_types": ["bank", "oa"],
            "amount_check": {"status": "matched", "bank_amount": "1872.93", "oa_amount": "1872.93"},
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1234",
                "oa_row_ids": ["oa-exp-1962"],
                "year": "2026",
            },
        }
        pair_service.record_history(
            operation_type="confirm_link",
            before_relations=[],
            after_relations=[lost_relation],
            affected_row_ids=list(lost_relation["row_ids"]),
            created_by="local_finops_admin",
            created_at="2026-05-19T02:58:05+00:00",
        )
        pair_service.record_history(
            operation_type="confirm_link",
            before_relations=[],
            after_relations=[later_relation],
            affected_row_ids=list(later_relation["row_ids"]),
            created_by="local_finops_admin",
            created_at="2026-05-19T03:43:10+00:00",
        )
        pair_service.create_active_relation(
            case_id="CASE-AUTO-0002",
            row_ids=["txn_imported_1234", "oa-exp-1962"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="local_finops_admin",
            special_metadata=later_relation["special_metadata"],
            amount_check=later_relation["amount_check"],
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
            relation_command_service=relation_command_service_for(pair_service),
        )

        result = service.repair_legacy_case_id_collisions()

        self.assertTrue(result["changed"])
        self.assertEqual(result["changed_case_ids"], ["CASE-BATCH-txn_imported_1263"])
        repaired = pair_service.get_active_relation_by_row_id("txn_imported_1263")
        assert repaired is not None
        self.assertEqual(repaired["case_id"], "CASE-BATCH-txn_imported_1263")
        self.assertEqual(repaired["special_metadata"]["legacy_case_id"], "CASE-AUTO-0002")
        self.assertEqual(repaired["special_metadata"]["repair_source"], "batch_accounting_case_id_collision")
        still_active = pair_service.get_active_relation_by_row_id("txn_imported_1234")
        assert still_active is not None
        self.assertEqual(still_active["case_id"], "CASE-AUTO-0002")
        self.assertEqual(pair_service.list_history()[-1]["operation_type"], "repair_batch_accounting_relation_id_collision")

    def test_repair_legacy_case_id_collision_does_not_restore_withdrawn_batch_relation(self) -> None:
        pair_service = WorkbenchPairRelationService()
        withdrawn_relation = {
            "case_id": "CASE-AUTO-0002",
            "row_ids": ["txn_imported_1263", "oa-exp-1981"],
            "row_types": ["bank", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "created_by": "local_finops_admin",
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1263",
                "oa_row_ids": ["oa-exp-1981"],
            },
        }
        pair_service.record_history(
            operation_type="confirm_link",
            before_relations=[],
            after_relations=[withdrawn_relation],
            affected_row_ids=list(withdrawn_relation["row_ids"]),
            created_by="local_finops_admin",
        )
        pair_service.record_history(
            operation_type="withdraw_link",
            before_relations=[withdrawn_relation],
            after_relations=[],
            affected_row_ids=list(withdrawn_relation["row_ids"]),
            created_by="local_finops_admin",
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
            relation_command_service=relation_command_service_for(pair_service),
        )

        result = service.repair_legacy_case_id_collisions()

        self.assertFalse(result["changed"])
        self.assertIsNone(pair_service.get_active_relation_by_row_id("txn_imported_1263"))

    def test_repair_legacy_case_id_collision_does_not_override_current_non_batch_relation(self) -> None:
        pair_service = WorkbenchPairRelationService()
        lost_relation = {
            "case_id": "CASE-AUTO-0002",
            "row_ids": ["txn_imported_1263", "oa-exp-1981"],
            "row_types": ["bank", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "created_by": "local_finops_admin",
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1263",
                "oa_row_ids": ["oa-exp-1981"],
            },
        }
        pair_service.record_history(
            operation_type="confirm_link",
            before_relations=[],
            after_relations=[lost_relation],
            affected_row_ids=list(lost_relation["row_ids"]),
            created_by="local_finops_admin",
        )
        pair_service.create_active_relation(
            case_id="CASE-MANUAL-CURRENT",
            row_ids=["txn_imported_1263", "oa-exp-current"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="finance-user",
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
            relation_command_service=relation_command_service_for(pair_service),
        )

        result = service.repair_legacy_case_id_collisions()

        self.assertFalse(result["changed"])
        active = pair_service.get_active_relation_by_row_id("txn_imported_1263")
        assert active is not None
        self.assertEqual(active["case_id"], "CASE-MANUAL-CURRENT")

    def test_repair_legacy_case_id_collision_uses_actual_bank_row_when_metadata_is_stale(self) -> None:
        pair_service = WorkbenchPairRelationService()
        stale_metadata_relation = {
            "case_id": "CASE-AUTO-0001",
            "row_ids": ["txn_imported_1240", "oa-exp-1952"],
            "row_types": ["bank", "oa"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-02",
            "created_by": "local_finops_admin",
            "special_metadata": {
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_1453",
                "oa_row_ids": ["oa-exp-1952"],
            },
        }
        pair_service.record_history(
            operation_type="confirm_link",
            before_relations=[],
            after_relations=[stale_metadata_relation],
            affected_row_ids=list(stale_metadata_relation["row_ids"]),
            created_by="local_finops_admin",
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: {},
            relation_command_service=relation_command_service_for(pair_service),
        )

        result = service.repair_legacy_case_id_collisions()

        self.assertEqual(result["changed_case_ids"], ["CASE-BATCH-txn_imported_1240"])
        self.assertIsNone(pair_service.get_active_relation_by_case_id("CASE-BATCH-txn_imported_1453"))
        repaired = pair_service.get_active_relation_by_row_id("txn_imported_1240")
        assert repaired is not None
        self.assertEqual(repaired["special_metadata"]["bank_row_id"], "txn_imported_1240")
        self.assertEqual(repaired["special_metadata"]["legacy_case_id"], "CASE-AUTO-0001")

    def test_submit_allows_cross_year_bank_and_oa_selection(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "bank_year": "2026",
                    "oa_year": "2025",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-2025", "oa-exp-ba-001"],
                    "actor": "finance-user",
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(payload["relation_id"])
        assert relation is not None
        self.assertEqual(relation["special_metadata"]["bank_year"], "2026")
        self.assertEqual(relation["special_metadata"]["oa_year"], "2025")
        self.assertEqual(relation["special_metadata"]["oa_years"], ["2025", "2026"])
        self.assertEqual(relation["special_metadata"]["year"], "2026")
        self.assertCountEqual(
            relation["row_ids"],
            [
                "txn_imported_202601_batch_001",
                "oa-exp-ba-2025",
                "oa-exp-ba-001",
                "oa-att-inv-oa-exp-ba-001-01",
            ],
        )

    def test_submitted_list_is_derived_from_active_batch_accounting_relations(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        submit_response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "actor": "finance-user",
                }
            ),
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001")
        self.assertIsNotNone(relation)
        app._workbench_relation_facade = FakeBatchRelationFacade(relation)

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=submitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["bank_rows"]], ["txn_imported_202601_batch_001"])
        relation_id = payload["bank_rows"][0]["relation_id"]
        self.assertTrue(relation_id)
        relation_payload = payload["relations_by_bank_row_id"]["txn_imported_202601_batch_001"]
        self.assertEqual(relation_payload["relation_id"], relation_id)
        self.assertEqual([row["id"] for row in relation_payload["oa_rows"]], ["oa-exp-ba-001", "oa-exp-ba-002"])
        self.assertEqual([row["id"] for row in relation_payload["invoice_rows"]], ["oa-att-inv-oa-exp-ba-001-01"])
        self.assertEqual(payload["summary"]["submitted_count"], 1)

    def test_submitted_list_relation_bucket_uses_workbench_relation_distribution(self) -> None:
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="CASE-BATCH-txn_imported_202601_batch_001",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-01",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_202601_batch_001",
                "oa_row_ids": ["oa-exp-ba-001"],
                "invoice_row_ids": [],
                "year": "2026",
            },
        )
        facade = FakeBatchRelationFacade()
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: self._grouped_payload(),
            relation_facade=facade,
        )

        payload = service.build_payload(year="2026", bucket="submitted")

        relation_payload = payload["relations_by_bank_row_id"]["txn_imported_202601_batch_001"]
        self.assertEqual([row["id"] for row in relation_payload["oa_rows"]], ["oa-exp-ba-001", "oa-exp-ba-002"])
        self.assertEqual(
            [row["id"] for row in relation_payload["invoice_rows"]],
            ["oa-att-inv-oa-exp-ba-001-01", "oa-att-inv-oa-exp-ba-002-01"],
        )
        month_calls = [call for call in facade.calls if call.get("month") == "2026-01"]
        self.assertTrue(month_calls)
        self.assertIn({"row_ids": ["txn_imported_202601_batch_001"], "require_fresh": True, "reason": "batch_accounting_submitted_relations"}, facade.calls)

    def test_submitted_list_exposes_relation_read_model_stale_status(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        app._workbench_relation_facade = NonFreshBatchRelationFacade(
            status="stale",
            stale_reasons=["dirty_scope:2026-01"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=True,
        )

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=submitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["read_model_stale_reasons"], ["dirty_scope:2026-01"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-01"])
        self.assertIs(payload["refresh_enqueued"], True)

    def test_submitted_list_exposes_mismatch_note_and_amount_check(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001")
        self.assertIsNotNone(relation)
        app._workbench_relation_facade = FakeBatchRelationFacade(relation)

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=submitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        relation_payload = payload["relations_by_bank_row_id"]["txn_imported_202601_batch_001"]
        self.assertEqual(relation_payload["relation"]["note"], "财务确认差额闭环")
        self.assertEqual(relation_payload["relation"]["amount_check"]["status"], "mismatch")
        self.assertTrue(relation_payload["relation"]["amount_check"]["requires_note"])

    def test_withdraw_does_not_restore_display_only_oa_invoice_snapshot_as_active_relation(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        submit_response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001", "oa-exp-ba-002"],
                    "actor": "finance-user",
                }
            ),
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.body)
        relation_id = json.loads(submit_response.body)["relation_id"]

        response = app.handle_request(
            "POST",
            f"/api/batch-accounting/{relation_id}/withdraw",
            json.dumps({"reason": "选择错误", "actor": "finance-user"}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["action"], "withdraw_batch_accounting")
        self.assertEqual(payload["affected_scope_keys"], ["2026-01", "all"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [
                {"read_model_key": "workbench_relation", "scope_key": "2026-01"},
                {"read_model_key": "workbench_relation", "scope_key": "all"},
            ],
        )
        self.assertEqual(payload["restored_relations"], [])
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-exp-ba-001"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-att-inv-oa-exp-ba-001-01"))
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["operation_type"], "withdraw_link")
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["after_relations"], [])

    def test_withdraw_delegates_relation_write_to_command_service(self) -> None:
        pair_service = WriteBlockingPairRelationService()
        pair_service.create_active_relation(
            case_id="CASE-BATCH-txn_imported_202601_batch_001",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="batch_accounting",
            created_by="finance-user",
            month_scope="2026-01",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_202601_batch_001",
                "oa_row_ids": ["oa-exp-ba-001"],
                "year": "2026",
            },
        )
        relation_command = RecordingBatchRelationCommandService(pair_service)
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: self._grouped_payload(),
            relation_facade=FakeBatchRelationFacade(),
            relation_command_service=relation_command,
        )

        result = service.withdraw(
            relation_id="CASE-BATCH-txn_imported_202601_batch_001",
            actor="finance-user",
            reason="选择错误",
        )

        self.assertEqual(result["action"], "withdraw_batch_accounting")
        self.assertEqual(len(relation_command.withdraw_calls), 1)
        call = relation_command.withdraw_calls[0]
        self.assertEqual(call["case_id"], "CASE-BATCH-txn_imported_202601_batch_001")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "选择错误")
        self.assertEqual(call["history_operation_type"], "withdraw_link")

    def test_withdraw_requires_relation_command_service_without_direct_pair_fallback(self) -> None:
        pair_service = WriteBlockingPairRelationService()
        pair_service.create_active_relation(
            case_id="CASE-BATCH-txn_imported_202601_batch_001",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="batch_accounting",
            created_by="finance-user",
            month_scope="2026-01",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_202601_batch_001",
                "oa_row_ids": ["oa-exp-ba-001"],
                "year": "2026",
            },
        )
        service = BatchAccountingService(
            grouped_workbench_loader=lambda _month: self._grouped_payload(),
            relation_facade=FakeBatchRelationFacade(),
        )

        with self.assertRaises(BatchAccountingError) as context:
            service.withdraw(
                relation_id="CASE-BATCH-txn_imported_202601_batch_001",
                actor="finance-user",
                reason="选择错误",
            )

        self.assertEqual(context.exception.code, "batch_accounting_relation_command_unavailable")

    def test_withdraw_mismatch_batch_preserves_submit_and_withdraw_notes(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        submit_payload = self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")
        relation_id = str(submit_payload["relation_id"])

        response = app.handle_request(
            "POST",
            f"/api/batch-accounting/{relation_id}/withdraw",
            json.dumps({"reason": "选错 OA", "actor": "finance-user"}),
        )

        self.assertEqual(response.status_code, 200, response.body)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(relation_id))
        histories = app._workbench_pair_relation_service.list_history()
        self.assertEqual(histories[-1]["operation_type"], "withdraw_link")
        self.assertEqual(histories[-1]["note"], "选错 OA")
        submit_history = next(history for history in histories if history["operation_type"] == "confirm_link")
        self.assertEqual(submit_history["note"], "财务确认差额闭环")
        self.assertEqual(submit_history["amount_check"]["status"], "mismatch")

    def test_withdraw_requires_reason_and_batch_accounting_relation(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-MANUAL",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )

        no_reason = app.handle_request(
            "POST",
            "/api/batch-accounting/CASE-MANUAL/withdraw",
            json.dumps({"reason": ""}),
        )
        self.assertEqual(no_reason.status_code, 400, no_reason.body)
        self.assertEqual(json.loads(no_reason.body)["error"], "batch_accounting_withdraw_reason_required")

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/CASE-MANUAL/withdraw",
            json.dumps({"reason": "误提交"}),
        )
        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(json.loads(response.body)["error"], "batch_accounting_relation_not_found")

    def test_withdraw_rejects_when_relation_read_model_is_not_fresh(self) -> None:
        app, _payload_patcher = self._app_with_grouped_payload()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-BATCH-txn_imported_202601_batch_001",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-01",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": "txn_imported_202601_batch_001",
                "oa_row_ids": ["oa-exp-ba-001"],
                "year": "2026",
            },
        )
        app._workbench_relation_facade = NonFreshBatchRelationFacade(
            status="stale",
            stale_reasons=["dirty_scope:2026-01"],
            read_model_scope_keys=["2026-01"],
            refresh_enqueued=True,
        )

        response = app.handle_request(
            "POST",
            "/api/batch-accounting/CASE-BATCH-txn_imported_202601_batch_001/withdraw",
            json.dumps({"reason": "选择错误", "actor": "finance-user"}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(payload["error"], "batch_accounting_read_model_not_fresh")
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["read_model_stale_reasons"], ["dirty_scope:2026-01"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-01"])
        self.assertIs(payload["refresh_enqueued"], True)
        self.assertIsNotNone(
            app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BATCH-txn_imported_202601_batch_001")
        )


if __name__ == "__main__":
    unittest.main()
