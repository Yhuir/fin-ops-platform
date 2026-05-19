from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


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

    def _app_with_grouped_payload(self) -> tuple[Application, patch]:
        app = build_application()
        payload_patcher = patch.object(app, "_build_api_workbench_payload", return_value=self._grouped_payload())
        payload_patcher.start()
        self.addCleanup(payload_patcher.stop)
        return app, payload_patcher

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
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-OTHER-LINK",
            row_ids=["txn_imported_202601_batch_001", "oa-exp-ba-001"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )

        response = app.handle_request("GET", "/api/batch-accounting?year=2026&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["bank_rows"], [])
        self.assertEqual(payload["summary"]["unsubmitted_count"], 0)

    def test_submit_rejects_amount_mismatch_without_trusting_frontend_amounts(self) -> None:
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
        self.assertEqual(payload["error"], "batch_accounting_amount_mismatch")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001"))

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
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
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
            pair_relation_service=pair_service,
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
            pair_relation_service=pair_service,
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
            pair_relation_service=pair_service,
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
            pair_relation_service=pair_service,
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

    def test_withdraw_restores_previous_oa_invoice_snapshot(self) -> None:
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
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_202601_batch_001"))
        restored = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-exp-ba-001")
        assert restored is not None
        self.assertEqual(restored["case_id"], "CASE-OA-INVOICE")
        self.assertCountEqual(restored["row_ids"], ["oa-exp-ba-001", "oa-att-inv-oa-exp-ba-001-01"])
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["operation_type"], "withdraw_link")

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


if __name__ == "__main__":
    unittest.main()
