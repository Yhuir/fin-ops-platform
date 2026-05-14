from __future__ import annotations

import unittest

from fin_ops_platform.services.no_oa_bank_batch_service import (
    NO_OA_BANK_BATCH_SCHEMA_VERSION,
    NoOaBankBatchService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


def bank_row(
    row_id: str,
    *,
    category_code: str,
    debit_amount: str = "",
    credit_amount: str = "",
    account_key: str = "CCB:8106",
    bank_name: str = "建行",
    account_no: str = "6222000000008106",
    pay_receive_time: str = "2026-03-10T09:00:00",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "category_code": category_code,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "account_key": account_key,
        "bank_name": bank_name,
        "account_no": account_no,
        "pay_receive_time": pay_receive_time,
        "account_name": "云南三源",
        "counterparty_name": "云南三源",
    }


def categories_for(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {
        str(row["id"]): {
            "transaction_id": row["id"],
            "category_code": row["category_code"],
            "category_label": {
                "fee": "手续费",
                "salary": "工资",
                "holiday_bonus": "过节费",
                "bonus": "奖金",
                "internal_transfer": "内部往来款",
            }[str(row["category_code"])],
            "category_source": "auto",
        }
        for row in rows
    }


class NoOaBankBatchServiceTests(unittest.TestCase):
    def test_fee_rows_are_grouped_by_account_month_and_type_as_draft(self) -> None:
        rows = [
            bank_row("fee-1", category_code="fee", debit_amount="3.00"),
            bank_row("fee-2", category_code="fee", debit_amount="2.50"),
            bank_row(
                "fee-3",
                category_code="fee",
                debit_amount="8.00",
                account_key="BOCOM:3847",
                bank_name="交行",
                account_no="6222000000003847",
            ),
        ]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), [], {})

        draft_batches = [batch for batch in batches if batch["status"] == "draft"]
        self.assertEqual(len(draft_batches), 2)
        ccb_batch = next(batch for batch in draft_batches if batch["account_key"] == "CCB:8106")
        self.assertEqual(ccb_batch["batch_type"], "fee")
        self.assertEqual(ccb_batch["scope_month"], "2026-03")
        self.assertEqual(ccb_batch["row_ids"], ["fee-1", "fee-2"])
        self.assertEqual(ccb_batch["row_count"], 2)
        self.assertEqual(ccb_batch["total_amount"], "5.50")

    def test_salary_holiday_bonus_and_bonus_rows_generate_drafts(self) -> None:
        rows = [
            bank_row("salary-1", category_code="salary", debit_amount="1000.00"),
            bank_row("holiday-1", category_code="holiday_bonus", debit_amount="200.00"),
            bank_row("bonus-1", category_code="bonus", debit_amount="300.00"),
        ]
        service = NoOaBankBatchService()

        service.build_batches(rows, categories_for(rows), [], {})

        by_type = {batch["batch_type"]: batch for batch in service.list_batches({"status": "draft"})}
        self.assertEqual(by_type["salary"]["batch_label"], "工资")
        self.assertEqual(by_type["holiday_bonus"]["batch_label"], "过节费")
        self.assertEqual(by_type["bonus"]["batch_label"], "奖金")

    def test_internal_transfer_pair_generates_draft_with_evidence(self) -> None:
        rows = [
            bank_row("transfer-out", category_code="internal_transfer", debit_amount="500.00"),
            bank_row(
                "transfer-in",
                category_code="internal_transfer",
                credit_amount="500.00",
                account_key="BOCOM:3847",
                bank_name="交行",
                account_no="6222000000003847",
                pay_receive_time="2026-03-10T10:00:00",
            ),
        ]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), [], {})

        batch = self.assert_single_batch(batches, "draft")
        self.assertEqual(batch["batch_type"], "internal_transfer")
        self.assertEqual(batch["income_row_ids"], ["transfer-in"])
        self.assertEqual(batch["expense_row_ids"], ["transfer-out"])
        self.assertEqual(batch["total_amount"], "500.00")
        self.assertEqual(batch["evidence"]["rule_code"], "internal_transfer_pair")
        self.assertEqual(batch["evidence"]["match_window_hours"], 48)

    def test_internal_transfer_multi_solution_generates_conflict(self) -> None:
        rows = [
            bank_row("transfer-out-1", category_code="internal_transfer", debit_amount="500.00"),
            bank_row(
                "transfer-out-2",
                category_code="internal_transfer",
                debit_amount="500.00",
                account_key="ABC:7777",
                bank_name="农行",
                account_no="6222000000007777",
            ),
            bank_row(
                "transfer-in-1",
                category_code="internal_transfer",
                credit_amount="500.00",
                account_key="BOCOM:3847",
                bank_name="交行",
                account_no="6222000000003847",
            ),
        ]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), [], {})

        batch = self.assert_single_batch(batches, "conflict")
        self.assertEqual(batch["conflict_code"], "multiple_internal_transfer_matches")

    def test_internal_transfer_single_sided_group_generates_conflict(self) -> None:
        rows = [bank_row("transfer-out", category_code="internal_transfer", debit_amount="500.00")]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), [], {})

        batch = self.assert_single_batch(batches, "conflict")
        self.assertEqual(batch["conflict_code"], "missing_internal_transfer_counterpart")

    def test_internal_transfer_occupied_by_active_relation_generates_conflict(self) -> None:
        rows = [
            bank_row("transfer-out", category_code="internal_transfer", debit_amount="500.00"),
            bank_row(
                "transfer-in",
                category_code="internal_transfer",
                credit_amount="500.00",
                account_key="BOCOM:3847",
                bank_name="交行",
                account_no="6222000000003847",
            ),
        ]
        active_relations = [{"case_id": "CASE-1", "status": "active", "row_ids": ["transfer-out"]}]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), active_relations, {})

        batch = self.assert_single_batch(batches, "conflict")
        self.assertEqual(batch["conflict_code"], "row_occupied_by_active_relation")

    def test_submit_batch_writes_no_oa_pair_relation_metadata_idempotently(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认")
        submitted_again = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=2, note="确认")

        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(submitted_again["batch_id"], submitted["batch_id"])
        relation = pair_service.get_active_relation_by_case_id(submitted["relation_case_id"])
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["special_metadata"]["source_batch_id"], submitted["batch_id"])
        self.assertEqual(relation["special_metadata"]["batch_type"], "fee")
        self.assertTrue(relation["special_metadata"]["withdrawable"])
        self.assertEqual(relation["display_tags"], ["免OA", "手续费"])
        self.assertEqual(len(pair_service.list_active_relations()), 1)

    def test_withdraw_batch_cancels_relation_and_marks_batch_withdrawn(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="")

        withdrawn = service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")
        withdrawn_again = service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=3, reason="误提交")

        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertEqual(withdrawn_again["status"], "withdrawn")
        self.assertIsNone(pair_service.get_active_relation_by_case_id(submitted["relation_case_id"]))
        self.assertEqual(withdrawn["withdraw_reason"], "误提交")

    def test_withdrawn_batch_rebuilds_as_draft_when_source_rows_remain_current(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="")
        withdrawn = service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")

        rebuilt = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")

        self.assertEqual(rebuilt["batch_id"], withdrawn["batch_id"])
        self.assertEqual(rebuilt["version"], withdrawn["version"] + 1)
        self.assertEqual(rebuilt["row_ids"], ["fee-1"])
        self.assertIsNone(pair_service.get_active_relation_by_case_id(submitted["relation_case_id"]))

    def test_snapshot_round_trip_preserves_batches_and_audit_log(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        service = NoOaBankBatchService()
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认")

        reloaded = NoOaBankBatchService.from_snapshot(service.snapshot())

        self.assertEqual(reloaded.snapshot(), service.snapshot())
        self.assertEqual(reloaded.snapshot()["schema_version"], NO_OA_BANK_BATCH_SCHEMA_VERSION)
        self.assertEqual(reloaded.audit_log()[-1]["operation"], "submit")

    def assert_single_batch(self, batches: list[dict[str, object]], status: str) -> dict[str, object]:
        matching = [batch for batch in batches if batch["status"] == status]
        self.assertEqual(len(matching), 1, batches)
        return matching[0]


if __name__ == "__main__":
    unittest.main()
