from __future__ import annotations

import json
import os
import pickle
from io import BytesIO
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from fin_ops_platform.app.routes_turnover_ledger import TurnoverLedgerApiRoutes
from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.state_store import ApplicationStateStore


class TurnoverLedgerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

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
        app._state_store.save_bank_transaction_categories(app._bank_transaction_category_service.snapshot())
        app._turnover_ledger_service.list_ledger()
        app._state_store.save_turnover_relations(app._turnover_relation_service.snapshot())

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

    def test_get_turnover_ledger_rebuilds_stale_sql_read_model_source_versions(self) -> None:
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

            def save_turnover_ledger_rows(self, payload: dict[str, object]) -> None:
                self.saved_payload = payload

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            repository = StaleTurnoverReadRepository()
            app._workbench_sql_read_repository = repository

            response = app.handle_request("GET", "/api/turnover-ledger")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rows"][0]["counterparty_name"], "梁希涛")
        self.assertNotEqual(payload["rows"][0]["relation_id"], "stale_sql_row")
        self.assertIsNotNone(repository.saved_payload)
        saved_payload = repository.saved_payload or {}
        self.assertEqual(saved_payload["source_versions"], app._turnover_ledger_source_versions())
        self.assertEqual(saved_payload["rows"][0]["source_versions"], app._turnover_ledger_source_versions())

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
            details_response = app.handle_request(
                "GET",
                f"/api/bank-details/transactions?category_code=borrow_in_company_pending_repayment",
            )
            details_payload = json.loads(details_response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["updated_categories"][0]["category_code"], "borrow_in_company_pending_repayment")
        self.assertTrue(payload["turnover_ledger_invalidated"])
        self.assertEqual(details_response.status_code, 200)
        self.assertEqual(details_payload["pagination"]["total"], 1)
        self.assertEqual(details_payload["rows"][0]["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(details_payload["rows"][0]["category_label"], "公司暂借款：待还款")

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
            audit_log = app._state_store.load_turnover_relation_audit_log()

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(withdrawn.status_code, 200)
        self.assertEqual([entry["action"] for entry in audit_log], ["confirm_relation", "withdraw_relation"])

    def test_withdraw_rejects_system_generated_relation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_ids = self._import_bank_rows(app)
            self._tag_rows(app, transaction_ids)
            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger").body)
            relation_id = ledger_payload["rows"][0]["relation_id"]

            response = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "不能撤回系统关系"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "system_relation_cannot_withdraw")

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
