from __future__ import annotations

import json
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
    def _group_bank_ids(group: dict[str, object]) -> list[str]:
        return [str(row["id"]) for row in list(group.get("bank_rows") or [])]

    def test_deterministic_turnover_relation_syncs_to_workbench_same_row(self) -> None:
        with self._temporary_app() as app:
            transaction_ids = self._import_bank_rows(app)
            self._tag_borrow_in_rows(app, transaction_ids)

            ledger_payload = json.loads(app.handle_request("GET", "/api/turnover-ledger?family=company").body)
            groups = self._workbench_open_groups(app)

        self.assertEqual(ledger_payload["rows"][0]["status"], "deterministic")
        turnover_groups = [
            group
            for group in groups
            if group.get("group_type") == "turnover_relation"
        ]
        self.assertEqual(len(turnover_groups), 1)
        self.assertEqual(self._group_bank_ids(turnover_groups[0]), transaction_ids)
        self.assertEqual(turnover_groups[0]["group_metadata"]["relation_status"], "deterministic")

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

    def test_confirm_and_withdraw_relation_updates_workbench_grouping(self) -> None:
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
        self.assertTrue([
            group
            for group in confirmed_groups
            if group.get("group_type") == "turnover_relation"
            and self._group_bank_ids(group) == transaction_ids
            and group["group_metadata"]["relation_status"] == "confirmed"
        ])
        self.assertFalse([
            group
            for group in withdrawn_groups
            if group.get("group_type") == "turnover_relation"
            and set(self._group_bank_ids(group)) == set(transaction_ids)
        ])


if __name__ == "__main__":
    unittest.main()
