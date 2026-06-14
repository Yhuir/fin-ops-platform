from __future__ import annotations

import json
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.domain.enums import BatchType


class TurnoverWorkbenchIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    @contextmanager
    def _temporary_app(self):
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            try:
                yield app
            finally:
                app.shutdown_background_jobs()

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

    def _import_bank_rows(
        self,
        app: Application,
        *,
        principal_amount: str = "200000.00",
        settlement_amount: str = "200000.00",
        counterparty_name: str = "梁希涛",
    ) -> list[str]:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="turnover-bank.xlsx",
            imported_by="YNSYLP005",
            rows=[
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-04",
                    "trade_time": "2026-03-04 13:00:00",
                    "pay_receive_time": "2026-03-04 13:00:00",
                    "counterparty_name": counterparty_name,
                    "debit_amount": "",
                    "credit_amount": principal_amount,
                    "summary": "电子汇入",
                    "remark": "暂借款",
                    "imported_bank_name": "建行",
                    "imported_bank_last4": "8106",
                },
                {
                    "account_no": "6222000011118106",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": "2026-03-05",
                    "trade_time": "2026-03-05 09:00:00",
                    "pay_receive_time": "2026-03-05 09:00:00",
                    "counterparty_name": counterparty_name,
                    "debit_amount": settlement_amount,
                    "credit_amount": "",
                    "summary": "电子转账",
                    "remark": "还暂借款",
                    "imported_bank_name": "建行",
                    "imported_bank_last4": "8106",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        return [transaction.id for transaction in app._import_service.list_transactions()]

    def _tag_borrow_in_rows(self, app: Application, transaction_ids: list[str]) -> None:
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
            actor="YNSYLP005",
        )
        app._turnover_ledger_service._selected_tag_codes_provider = None
        app._state_store.save_bank_transaction_categories(
            app._bank_transaction_category_service.snapshot()
        )

    @staticmethod
    def _workbench_open_groups(app: Application) -> list[dict[str, object]]:
        response = app.handle_request("GET", "/api/workbench?month=2026-03")
        payload = json.loads(response.body)
        return list(payload["open"]["groups"])

    @staticmethod
    def _workbench_paired_groups(app: Application) -> list[dict[str, object]]:
        response = app.handle_request("GET", "/api/workbench?month=2026-03")
        payload = json.loads(response.body)
        return list(payload["paired"]["groups"])

    @staticmethod
    def _group_bank_ids(group: dict[str, object]) -> list[str]:
        return [str(row["id"]) for row in list(group.get("bank_rows") or [])]

    def test_deterministic_turnover_relation_does_not_sync_to_workbench_without_manual_closure(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)

            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger?family=company").body)
            groups = self._workbench_open_groups(app)

        self.assertEqual(ledger_payload["rows"][0]["status"], "deterministic")
        self.assertFalse([
            group
            for group in groups
            if group.get("group_type") == "turnover_relation"
            and set(self._group_bank_ids(group)) == set(transaction_ids)
        ])

    def test_suggested_partial_turnover_relation_does_not_sync_to_workbench_same_row(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app, settlement_amount="100000.00")
            self._tag_borrow_in_rows(app, transaction_ids)

            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger?family=company").body)
            groups = self._workbench_open_groups(app)

        self.assertEqual(ledger_payload["rows"][0]["status"], "suggested")
        self.assertFalse([group for group in groups if group.get("group_type") == "turnover_relation"])
        self.assertFalse([
            group
            for group in groups
            if set(self._group_bank_ids(group)) == set(transaction_ids)
        ])

    def test_legacy_confirm_and_withdraw_relation_do_not_sync_to_workbench_grouping(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app, settlement_amount="100000.00")
            self._tag_borrow_in_rows(app, transaction_ids)

            confirmed = app.handle_request(
                "POST",
                "/api/turnover-ledger/relations/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "人工确认同一笔往来"}),
            )
            confirmed_payload = json.loads(confirmed.body)
            confirmed_groups = self._workbench_open_groups(app)

            withdrawn = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{confirmed_payload['relation']['relation_id']}/withdraw",
                body=json.dumps({"note": "撤销归并"}),
            )
            withdrawn_groups = self._workbench_open_groups(app)

        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(withdrawn.status_code, 200)
        self.assertFalse([
            group
            for group in confirmed_groups
            if group.get("group_type") == "turnover_relation"
            and set(self._group_bank_ids(group)) == set(transaction_ids)
        ])
        self.assertFalse([
            group
            for group in withdrawn_groups
            if group.get("group_type") == "turnover_relation"
            and set(self._group_bank_ids(group)) == set(transaction_ids)
        ])

    def test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "外部往来手动闭环"}),
            )
            payload = json.loads(response.body)
            paired_groups = self._workbench_paired_groups(app)
            open_groups = self._workbench_open_groups(app)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["turnover_relation"]["status"], "confirmed")
        self.assertEqual(payload["workbench_pair_relation"]["relation_mode"], "turnover_manual_closure")
        self.assertFalse([
            group
            for group in paired_groups
            if set(self._group_bank_ids(group)) == set(transaction_ids)
        ])
        self.assertTrue([
            group
            for group in open_groups
            if set(self._group_bank_ids(group)) == set(transaction_ids)
        ])

    def test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale(self) -> None:
        class StaleWorkbenchRelationFacade:
            def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "stale",
                    "rows": [],
                    "groups": [],
                    "read_model_scope_keys": ["2026-03"],
                    "stale_reasons": ["source_version_mismatch"],
                    "refresh_enqueued": True,
                }

        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)
            app._workbench_relation_facade = StaleWorkbenchRelationFacade()
            before_turnover_snapshot = app._turnover_relation_service.snapshot()
            before_pair_snapshot = app._workbench_pair_relation_service.snapshot()

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "外部往来手动闭环"}),
            )
            payload = json.loads(response.body)

            after_turnover_snapshot = app._turnover_relation_service.snapshot()
            after_pair_snapshot = app._workbench_pair_relation_service.snapshot()

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["turnover_relation"]["status"], "confirmed")
        self.assertEqual(payload["workbench_pair_relation"]["status"], "active")
        self.assertEqual(payload["workbench_pair_relation"]["relation_mode"], "turnover_manual_closure")
        self.assertEqual(set(payload["workbench_pair_relation"]["row_ids"]), set(transaction_ids))
        self.assertEqual(payload["affected_months"], ["2026-03"])
        self.assertNotEqual(after_turnover_snapshot, before_turnover_snapshot)
        self.assertNotEqual(after_pair_snapshot, before_pair_snapshot)

    def test_manual_closure_accepts_source_bank_row_ids_from_grouped_read_model(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app, principal_amount="40000.00", settlement_amount="40000.00")
            self._tag_borrow_in_rows(app, transaction_ids)
            canonical_rows = app._turnover_bank_transaction_rows()
            aliased_rows = [
                {
                    **row,
                    "id": f"postgres-{row['id']}",
                    "source_bank_row_id": row["id"],
                }
                for row in canonical_rows
            ]
            app._turnover_bank_transaction_rows = lambda: aliased_rows  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "外部往来手动闭环"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["turnover_relation"]["status"], "confirmed")
        self.assertEqual(set(payload["turnover_relation"]["bank_row_ids"]), set(transaction_ids))
        self.assertEqual(payload["workbench_pair_relation"]["relation_mode"], "turnover_manual_closure")

    def test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_open(self) -> None:
        with self._temporary_app() as app:
            preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="turnover-bank-three.xlsx",
                imported_by="YNSYLP005",
                rows=[
                    {
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司基本户",
                        "txn_date": "2026-03-04",
                        "trade_time": "2026-03-04 13:00:00",
                        "pay_receive_time": "2026-03-04 13:00:00",
                        "counterparty_name": "梁希涛",
                        "debit_amount": "",
                        "credit_amount": "200000.00",
                        "summary": "电子汇入",
                        "remark": "暂借款",
                    },
                    {
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司基本户",
                        "txn_date": "2026-03-04",
                        "trade_time": "2026-03-04 13:20:00",
                        "pay_receive_time": "2026-03-04 13:20:00",
                        "counterparty_name": "梁希涛",
                        "debit_amount": "",
                        "credit_amount": "100000.00",
                        "summary": "电子汇入",
                        "remark": "暂借款",
                    },
                    {
                        "account_no": "6222000011118106",
                        "account_name": "云南溯源科技有限公司基本户",
                        "txn_date": "2026-03-05",
                        "trade_time": "2026-03-05 09:00:00",
                        "pay_receive_time": "2026-03-05 09:00:00",
                        "counterparty_name": "梁希涛",
                        "debit_amount": "300000.00",
                        "credit_amount": "",
                        "summary": "电子转账",
                        "remark": "还暂借款",
                    },
                ],
            )
            app._import_service.confirm_import(preview.id)
            transaction_ids = [transaction.id for transaction in app._import_service.list_transactions()]
            app._bank_transaction_category_service.apply_updates(
                [
                    {
                        "transaction_id": transaction_ids[0],
                        "category_code": "borrow_in_company_pending_repayment",
                        "expected_version": 0,
                    },
                    {
                        "transaction_id": transaction_ids[1],
                        "category_code": "borrow_in_company_pending_repayment",
                        "expected_version": 0,
                    },
                    {
                        "transaction_id": transaction_ids[2],
                        "category_code": "borrow_in_company_repaid",
                        "expected_version": 0,
                    },
                ],
                actor="YNSYLP005",
            )
            app._turnover_ledger_service._selected_tag_codes_provider = None
            app._state_store.save_bank_transaction_categories(
                app._bank_transaction_category_service.snapshot()
            )

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "三笔外部往来手动闭环"}),
            )
            payload = json.loads(response.body)
            paired_groups = self._workbench_paired_groups(app)
            open_groups = self._workbench_open_groups(app)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["turnover_relation"]["evidence"]["closure_mode"], "manual_zero_difference_group")
        self.assertEqual(
            payload["workbench_pair_relation"]["special_metadata"]["turnover_closure_mode"],
            "manual_zero_difference_group",
        )
        self.assertEqual(set(payload["turnover_relation"]["bank_row_ids"]), set(transaction_ids))
        self.assertFalse([
            group
            for group in paired_groups
            if set(self._group_bank_ids(group)) == set(transaction_ids)
        ])
        self.assertTrue([
            group
            for group in open_groups
            if set(self._group_bank_ids(group)) == set(transaction_ids)
        ])

    def test_turnover_withdraw_rejects_after_workbench_relation_is_upgraded_to_three_panes(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)
            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "外部往来手动闭环"}),
            )
            payload = json.loads(response.body)
            relation_id = str(payload["turnover_relation"]["relation_id"])
            case_id = f"turnover:{relation_id}"
            app._workbench_pair_relation_service.create_active_relation(
                case_id=case_id,
                row_ids=["oa-upgraded-1", *transaction_ids, "invoice-upgraded-1"],
                row_types=["oa", "bank", "bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="YNSYLP005",
                note="关联台补齐三栏",
            )

            withdraw = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "外部往来页撤回"}),
            )
            withdraw_payload = json.loads(withdraw.body)

        self.assertEqual(withdraw.status_code, 409)
        self.assertEqual(withdraw_payload["error"], "turnover_closure_withdraw_requires_workbench")

    def test_turnover_withdraw_bank_only_closure_cancels_workbench_relation(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)
            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids, "note": "外部往来手动闭环"}),
            )
            payload = json.loads(response.body)
            relation_id = str(payload["turnover_relation"]["relation_id"])
            case_id = f"turnover:{relation_id}"
            self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(case_id))

            withdraw = app.handle_request(
                "POST",
                f"/api/turnover-ledger/relations/{relation_id}/withdraw",
                body=json.dumps({"note": "撤回 bank-only 闭环"}),
            )
            withdraw_payload = json.loads(withdraw.body)
            active_after = app._workbench_pair_relation_service.get_active_relation_by_case_id(case_id)

        self.assertEqual(withdraw.status_code, 200)
        self.assertEqual(withdraw_payload["relation"]["status"], "withdrawn")
        self.assertEqual(withdraw_payload["workbench_pair_relation"]["status"], "cancelled")
        self.assertIsNone(active_after)

    def test_manual_closure_rejects_non_zero_difference(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app, settlement_amount="100000.00")
            self._tag_borrow_in_rows(app, transaction_ids)

            response = app.handle_request(
                "POST",
                "/api/turnover-ledger/closures/confirm",
                body=json.dumps({"bank_row_ids": transaction_ids}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "turnover_closure_amount_mismatch")

    def test_manual_closure_requires_mutation_permission(self) -> None:
        with self._without_default_test_auth():
            with self._temporary_app() as app:
                response = app.handle_request(
                    "POST",
                    "/api/turnover-ledger/closures/confirm",
                    body=json.dumps({"bank_row_ids": ["bank-1", "bank-2"]}),
                )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
