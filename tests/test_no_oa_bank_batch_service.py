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
                "tax_payment": "税款",
                "treasury_tax_collection": "代理国库税收收缴",
                "social_security": "社保款",
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
        self.assertEqual(ccb_batch["status_bucket"], "unsubmitted")
        self.assertEqual(ccb_batch["tag_counts"], {"fee": 2})
        self.assertEqual(ccb_batch["direction_counts"], {"income": 0, "expense": 2})
        self.assertTrue(ccb_batch["can_submit"])
        self.assertFalse(ccb_batch["can_withdraw"])
        self.assertEqual(ccb_batch["blocked_reason"], "")

    def test_new_fee_rows_after_submitted_same_month_account_batch_generate_incremental_draft(self) -> None:
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        submitted_rows = [bank_row("fee-submitted", category_code="fee", debit_amount="0.90")]
        submitted_batch = self.assert_single_batch(
            service.build_batches(submitted_rows, categories_for(submitted_rows), [], {}),
            "draft",
        )
        service.submit_batch(submitted_batch["batch_id"], actor="finance-user", expected_version=1, note="确认")
        current_rows = [
            *submitted_rows,
            bank_row("fee-new", category_code="fee", debit_amount="1.25"),
        ]

        batches = service.build_batches(
            current_rows,
            categories_for(current_rows),
            pair_service.list_active_relations(),
            {},
        )

        submitted = [batch for batch in batches if batch["status"] == "submitted" and batch["batch_type"] == "fee"]
        drafts = [batch for batch in batches if batch["status"] == "draft" and batch["batch_type"] == "fee"]
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0]["row_ids"], ["fee-submitted"])
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["row_ids"], ["fee-new"])
        self.assertEqual(drafts[0]["total_amount"], "1.25")
        self.assertNotEqual(drafts[0]["batch_id"], submitted[0]["batch_id"])

    def test_salary_holiday_bonus_and_bonus_rows_generate_drafts(self) -> None:
        rows = [
            bank_row("salary-1", category_code="salary", debit_amount="1000.00"),
            bank_row("holiday-1", category_code="holiday_bonus", debit_amount="200.00"),
            bank_row("bonus-1", category_code="bonus", debit_amount="300.00"),
            bank_row("tax-1", category_code="tax_payment", debit_amount="400.00"),
            bank_row("treasury-tax-1", category_code="treasury_tax_collection", debit_amount="500.00"),
            bank_row("social-security-1", category_code="social_security", debit_amount="600.00"),
        ]
        service = NoOaBankBatchService()

        service.build_batches(rows, categories_for(rows), [], {})

        by_type = {batch["batch_type"]: batch for batch in service.list_batches({"status": "draft"})}
        self.assertEqual(by_type["salary"]["batch_label"], "工资")
        self.assertEqual(by_type["holiday_bonus"]["batch_label"], "过节费")
        self.assertEqual(by_type["bonus"]["batch_label"], "奖金")
        self.assertEqual(by_type["tax_payment"]["batch_label"], "税款")
        self.assertEqual(by_type["treasury_tax_collection"]["batch_label"], "代理国库税收收缴")
        self.assertEqual(by_type["social_security"]["batch_label"], "社保款")

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
        self.assertEqual(batch["status_bucket"], "unsubmitted")
        self.assertEqual(batch["tag_counts"], {"internal_transfer": 3})
        self.assertEqual(batch["direction_counts"], {"income": 1, "expense": 2})
        self.assertFalse(batch["can_submit"])
        self.assertFalse(batch["can_withdraw"])
        self.assertEqual(batch["blocked_reason"], "内部往来存在多解，不能自动形成可提交批次。")

    def test_internal_transfer_equal_multi_rows_pair_by_nearest_time(self) -> None:
        rows = [
            bank_row(
                "transfer-in-late",
                category_code="internal_transfer",
                credit_amount="4000.00",
                account_key="ICBC:6386",
                bank_name="工商银行",
                account_no="6386",
                pay_receive_time="2026-04-16T11:18:05",
            ),
            bank_row(
                "transfer-in-early",
                category_code="internal_transfer",
                credit_amount="4000.00",
                account_key="ICBC:6386",
                bank_name="工商银行",
                account_no="6386",
                pay_receive_time="2026-04-16T11:09:16",
            ),
            bank_row(
                "transfer-out-late",
                category_code="internal_transfer",
                debit_amount="4000.00",
                account_key="CCB:8106",
                bank_name="建设银行",
                account_no="8106",
                pay_receive_time="2026-04-16T11:17:51",
            ),
            bank_row(
                "transfer-out-early",
                category_code="internal_transfer",
                debit_amount="4000.00",
                account_key="CCB:8106",
                bank_name="建设银行",
                account_no="8106",
                pay_receive_time="2026-04-16T11:09:13",
            ),
        ]
        service = NoOaBankBatchService()

        batches = service.build_batches(rows, categories_for(rows), [], {})

        draft_batches = sorted(
            [batch for batch in batches if batch["status"] == "draft"],
            key=lambda batch: batch["evidence"]["time_delta_seconds"],
        )
        self.assertEqual(len(draft_batches), 2)
        self.assertEqual([batch for batch in batches if batch["status"] == "conflict"], [])
        self.assertEqual(draft_batches[0]["income_row_ids"], ["transfer-in-early"])
        self.assertEqual(draft_batches[0]["expense_row_ids"], ["transfer-out-early"])
        self.assertEqual(draft_batches[0]["evidence"]["time_delta_seconds"], 3)
        self.assertEqual(draft_batches[1]["income_row_ids"], ["transfer-in-late"])
        self.assertEqual(draft_batches[1]["expense_row_ids"], ["transfer-out-late"])
        self.assertEqual(draft_batches[1]["evidence"]["time_delta_seconds"], 14)

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

    def test_submitted_internal_transfer_no_oa_relation_does_not_rebuild_as_conflict(self) -> None:
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
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(
            service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {}),
            "draft",
        )
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认")

        refreshed = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})

        self.assertEqual([item["status"] for item in refreshed], ["submitted"])
        self.assertEqual(refreshed[0]["batch_id"], submitted["batch_id"])
        self.assertEqual(service.list_batches({"bucket": "unsubmitted"}), [])

    def test_legacy_salary_relation_migrates_to_submitted_no_oa_batch_idempotently(self) -> None:
        rows = [bank_row("salary-1", category_code="salary", debit_amount="1000.00")]
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="salary_auto_history",
            row_ids=["salary-1"],
            row_types=["bank"],
            relation_mode="salary_personal_auto_match",
            created_by="system_auto_match",
            month_scope="2026-03",
            special_metadata={"legacy_marker": "keep"},
        )
        service = NoOaBankBatchService(pair_relation_service=pair_service)

        migrated = self.assert_single_batch(
            service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {}),
            "submitted",
        )
        service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})

        self.assertEqual(migrated["batch_type"], "salary")
        self.assertEqual(migrated["row_ids"], ["salary-1"])
        self.assertEqual(migrated["submitted_by"], "no_oa_legacy_relation_migration")
        self.assertIsNone(pair_service.get_active_relation_by_case_id("salary_auto_history"))
        active_relations = pair_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        relation = active_relations[0]
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["row_ids"], ["salary-1"])
        self.assertEqual(relation["special_metadata"]["source_batch_id"], migrated["batch_id"])
        self.assertEqual(relation["special_metadata"]["legacy_relation_mode"], "salary_personal_auto_match")
        self.assertEqual(relation["special_metadata"]["legacy_case_id"], "salary_auto_history")
        self.assertEqual(relation["special_metadata"]["migration_source"], "no_oa_legacy_relation_migration")
        self.assertEqual(len(service.audit_log()), 1)

    def test_legacy_salary_relations_same_month_account_aggregate_to_one_submitted_batch(self) -> None:
        rows = [
            bank_row("salary-1", category_code="salary", debit_amount="1000.00"),
            bank_row("salary-2", category_code="salary", debit_amount="1500.50"),
            bank_row("salary-3", category_code="salary", debit_amount="2000.25"),
            bank_row("salary-4", category_code="salary", debit_amount="499.25"),
        ]
        pair_service = WorkbenchPairRelationService()
        for row in rows:
            row_id = str(row["id"])
            pair_service.create_active_relation(
                case_id=f"{row_id}_auto_history",
                row_ids=[row_id],
                row_types=["bank"],
                relation_mode="salary_personal_auto_match",
                created_by="system_auto_match",
                month_scope="2026-03",
                special_metadata={"legacy_marker": row_id},
            )
        service = NoOaBankBatchService(pair_relation_service=pair_service)

        first_refresh = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})
        migrated = self.assert_single_batch(first_refresh, "submitted")
        second_refresh = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})

        self.assertEqual(migrated["batch_type"], "salary")
        self.assertEqual(migrated["batch_key"], "legacy_single:salary:2026-03:CCB:8106")
        self.assertEqual(migrated["row_ids"], ["salary-1", "salary-2", "salary-3", "salary-4"])
        self.assertEqual(migrated["row_count"], 4)
        self.assertEqual(migrated["total_amount"], "5000.00")
        self.assertEqual(migrated["tag_counts"], {"salary": 4})
        self.assertEqual(migrated["direction_counts"], {"income": 0, "expense": 4})
        self.assertEqual(migrated["evidence"]["migration_source"], "no_oa_legacy_relation_migration")
        self.assertEqual(
            [item["legacy_case_id"] for item in migrated["evidence"]["legacy_relations"]],
            [
                "salary-1_auto_history",
                "salary-2_auto_history",
                "salary-3_auto_history",
                "salary-4_auto_history",
            ],
        )
        self.assertTrue(
            all(
                pair_service.get_active_relation_by_case_id(f"salary-{index}_auto_history") is None
                for index in range(1, 5)
            )
        )
        active_relations = pair_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        relation = active_relations[0]
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["row_ids"], ["salary-1", "salary-2", "salary-3", "salary-4"])
        self.assertEqual(relation["special_metadata"]["source_batch_id"], migrated["batch_id"])
        self.assertEqual(
            [item["legacy_case_id"] for item in relation["special_metadata"]["legacy_relations"]],
            [
                "salary-1_auto_history",
                "salary-2_auto_history",
                "salary-3_auto_history",
                "salary-4_auto_history",
            ],
        )
        self.assertEqual(self.assert_single_batch(second_refresh, "submitted")["batch_id"], migrated["batch_id"])
        self.assertEqual(len(service.audit_log()), 1)

    def test_existing_submitted_single_row_salary_batches_consolidate_by_month_and_account(self) -> None:
        rows = [
            bank_row("salary-1", category_code="salary", debit_amount="1000.00"),
            bank_row("salary-2", category_code="salary", debit_amount="1500.50"),
            bank_row("salary-3", category_code="salary", debit_amount="2000.25"),
        ]
        pair_service = WorkbenchPairRelationService()
        old_batches: dict[str, dict[str, object]] = {}
        for row in rows:
            row_id = str(row["id"])
            old_batch_key = f"legacy:salary_personal_auto_match:{row_id}_auto_history:{row_id}"
            old_batch_id = NoOaBankBatchService._batch_id(old_batch_key)
            old_batches[old_batch_id] = {
                "batch_id": old_batch_id,
                "batch_key": old_batch_key,
                "batch_type": "salary",
                "batch_label": "工资",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "bank_name": "建行",
                "account_last4": "8106",
                "status": "submitted",
                "row_ids": [row_id],
                "row_count": 1,
                "total_amount": row["debit_amount"],
                "tag_counts": {"salary": 1},
                "direction_counts": {"income": 0, "expense": 1},
                "relation_case_id": old_batch_id,
                "evidence": {
                    "legacy_relation_mode": "salary_personal_auto_match",
                    "legacy_case_id": f"{row_id}_auto_history",
                    "migration_source": "no_oa_legacy_relation_migration",
                    "migrated_at": "2026-05-15T00:00:00+00:00",
                },
                "category_source": "legacy_relation_migration",
                "created_by": "no_oa_legacy_relation_migration",
                "created_at": "2026-05-15T00:00:00+00:00",
                "submitted_by": "no_oa_legacy_relation_migration",
                "submitted_at": "2026-05-15T00:00:00+00:00",
                "version": 1,
                "updated_at": "2026-05-15T00:00:00+00:00",
            }
            pair_service.create_active_relation(
                case_id=old_batch_id,
                row_ids=[row_id],
                row_types=["bank"],
                relation_mode="no_oa_bank_batch",
                created_by="no_oa_legacy_relation_migration",
                month_scope="2026-03",
                special_metadata={
                    "source": "no_oa_bank_batch",
                    "source_batch_id": old_batch_id,
                    "batch_type": "salary",
                    "batch_label": "工资",
                    "relation_mode": "no_oa_bank_batch",
                },
                display_tags=["免OA", "工资"],
            )
        service = NoOaBankBatchService(batches=old_batches, pair_relation_service=pair_service)

        first_refresh = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})
        second_refresh = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})

        consolidated = self.assert_single_batch(first_refresh, "submitted")
        self.assertEqual(consolidated["batch_key"], "legacy_single:salary:2026-03:CCB:8106")
        self.assertEqual(consolidated["row_ids"], ["salary-1", "salary-2", "salary-3"])
        self.assertEqual(consolidated["row_count"], 3)
        self.assertEqual(consolidated["total_amount"], "4500.75")
        self.assertEqual(consolidated["tag_counts"], {"salary": 3})
        self.assertEqual(consolidated["evidence"]["consolidation_source"], "submitted_no_oa_single_side_batches")
        self.assertCountEqual(consolidated["evidence"]["superseded_batch_ids"], list(old_batches))
        self.assertEqual(self.assert_single_batch(second_refresh, "submitted")["batch_id"], consolidated["batch_id"])
        self.assertEqual(service.list_batches({"status": "superseded"}), [])
        self.assertTrue(
            all(pair_service.get_active_relation_by_case_id(batch_id) is None for batch_id in old_batches)
        )
        active_relations = pair_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["case_id"], consolidated["relation_case_id"])
        self.assertEqual(active_relations[0]["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(active_relations[0]["row_ids"], ["salary-1", "salary-2", "salary-3"])
        self.assertEqual(active_relations[0]["special_metadata"]["source_batch_id"], consolidated["batch_id"])
        self.assertEqual(active_relations[0]["special_metadata"]["batch_type"], "salary")
        self.assertCountEqual(active_relations[0]["special_metadata"]["superseded_batch_ids"], list(old_batches))
        self.assertEqual(len(service.audit_log()), 1)

    def test_consolidated_submitted_salary_batch_repairs_stale_single_row_relations(self) -> None:
        rows = [
            bank_row("salary-1", category_code="salary", debit_amount="1000.00"),
            bank_row("salary-2", category_code="salary", debit_amount="1500.50"),
            bank_row("salary-3", category_code="salary", debit_amount="2000.25"),
        ]
        consolidated_batch_key = "legacy_single:salary:2026-03:CCB:8106"
        consolidated_batch_id = NoOaBankBatchService._batch_id(consolidated_batch_key)
        old_batch_ids = [
            NoOaBankBatchService._batch_id(f"legacy:salary_personal_auto_match:{row['id']}_auto_history:{row['id']}")
            for row in rows
        ]
        batches: dict[str, dict[str, object]] = {
            consolidated_batch_id: {
                "batch_id": consolidated_batch_id,
                "batch_key": consolidated_batch_key,
                "batch_type": "salary",
                "batch_label": "工资",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "bank_name": "建行",
                "account_last4": "8106",
                "status": "submitted",
                "row_ids": ["salary-1", "salary-2", "salary-3"],
                "row_count": 3,
                "total_amount": "4500.75",
                "tag_counts": {"salary": 3},
                "direction_counts": {"income": 0, "expense": 3},
                "relation_case_id": consolidated_batch_id,
                "evidence": {
                    "source": "submitted_no_oa_single_side_batches",
                    "consolidation_source": "submitted_no_oa_single_side_batches",
                    "superseded_batch_ids": old_batch_ids,
                    "source_relation_case_ids": old_batch_ids,
                },
                "category_source": "submitted_no_oa_consolidation",
                "created_by": "no_oa_legacy_relation_migration",
                "created_at": "2026-05-15T00:00:00+00:00",
                "submitted_by": "no_oa_legacy_relation_migration",
                "submitted_at": "2026-05-15T00:00:00+00:00",
                "version": 1,
                "updated_at": "2026-05-15T00:00:00+00:00",
            }
        }
        pair_service = WorkbenchPairRelationService()
        for row, old_batch_id in zip(rows, old_batch_ids, strict=True):
            row_id = str(row["id"])
            batches[old_batch_id] = {
                "batch_id": old_batch_id,
                "batch_key": f"legacy:salary_personal_auto_match:{row_id}_auto_history:{row_id}",
                "batch_type": "salary",
                "batch_label": "工资",
                "scope_month": "2026-03",
                "account_key": "CCB:8106",
                "bank_name": "建行",
                "account_last4": "8106",
                "status": "superseded",
                "row_ids": [row_id],
                "row_count": 1,
                "total_amount": row["debit_amount"],
                "tag_counts": {"salary": 1},
                "direction_counts": {"income": 0, "expense": 1},
                "relation_case_id": old_batch_id,
                "evidence": {
                    "superseded_by_batch_id": consolidated_batch_id,
                    "consolidation_source": "submitted_no_oa_single_side_batches",
                },
                "version": 2,
            }
            pair_service.create_active_relation(
                case_id=old_batch_id,
                row_ids=[row_id],
                row_types=["bank"],
                relation_mode="no_oa_bank_batch",
                created_by="no_oa_legacy_relation_migration",
                month_scope="2026-03",
                special_metadata={
                    "source": "no_oa_bank_batch",
                    "source_batch_id": old_batch_id,
                    "batch_type": "salary",
                    "batch_label": "工资",
                    "relation_mode": "no_oa_bank_batch",
                },
                display_tags=["免OA", "工资"],
            )
        service = NoOaBankBatchService(batches=batches, pair_relation_service=pair_service)

        refreshed = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})

        submitted = self.assert_single_batch(refreshed, "submitted")
        self.assertEqual(submitted["batch_id"], consolidated_batch_id)
        self.assertTrue(service.last_legacy_migration_result()["changed"])
        active_relations = pair_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["case_id"], consolidated_batch_id)
        self.assertEqual(active_relations[0]["row_ids"], ["salary-1", "salary-2", "salary-3"])
        self.assertEqual(active_relations[0]["special_metadata"]["source_batch_id"], consolidated_batch_id)
        self.assertTrue(all(pair_service.get_active_relation_by_case_id(batch_id) is None for batch_id in old_batch_ids))

    def test_legacy_internal_transfer_relation_migrates_to_submitted_no_oa_batch(self) -> None:
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
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="internal_transfer_history",
            row_ids=["transfer-out", "transfer-in"],
            row_types=["bank", "bank"],
            relation_mode="internal_transfer_pair",
            created_by="system_auto_match",
            month_scope="2026-03",
        )
        service = NoOaBankBatchService(pair_relation_service=pair_service)

        batches = service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {})
        migrated = self.assert_single_batch(batches, "submitted")

        self.assertEqual(migrated["batch_type"], "internal_transfer")
        self.assertEqual(migrated["income_row_ids"], ["transfer-in"])
        self.assertEqual(migrated["expense_row_ids"], ["transfer-out"])
        self.assertEqual(migrated["evidence"]["legacy_relation_mode"], "internal_transfer_pair")
        self.assertEqual(migrated["evidence"]["legacy_case_id"], "internal_transfer_history")
        self.assertIsNone(pair_service.get_active_relation_by_case_id("internal_transfer_history"))
        relation = pair_service.list_active_relations()[0]
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["special_metadata"]["batch_type"], "internal_transfer")
        self.assertEqual(relation["special_metadata"]["cost_policy"], "exclude_all")
        self.assertEqual([batch for batch in batches if batch["status"] == "conflict"], [])

    def test_reclassified_legacy_relation_is_cancelled_instead_of_remaining_paired(self) -> None:
        rows = [bank_row("salary-1", category_code="fee", debit_amount="10.00")]
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="salary_auto_history",
            row_ids=["salary-1"],
            row_types=["bank"],
            relation_mode="salary_personal_auto_match",
            created_by="system_auto_match",
            month_scope="2026-03",
        )
        service = NoOaBankBatchService(pair_relation_service=pair_service)

        draft = self.assert_single_batch(
            service.build_batches(rows, categories_for(rows), pair_service.list_active_relations(), {}),
            "draft",
        )
        migration_result = service.last_legacy_migration_result()

        self.assertEqual(draft["batch_type"], "fee")
        self.assertIsNone(pair_service.get_active_relation_by_case_id("salary_auto_history"))
        self.assertEqual(pair_service.list_active_relations(), [])
        self.assertTrue(migration_result["changed"])
        self.assertEqual(migration_result["changed_case_ids"], ["salary_auto_history"])
        self.assertEqual(migration_result["skipped"][0]["reason"], "legacy_relation_category_mismatch")

    def test_submit_batch_writes_no_oa_pair_relation_metadata_idempotently(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认")
        submitted_again = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=2, note="确认")

        self.assertEqual(submitted["status"], "submitted")
        self.assertEqual(submitted["status_bucket"], "submitted")
        self.assertFalse(submitted["can_submit"])
        self.assertTrue(submitted["can_withdraw"])
        self.assertEqual(submitted["blocked_reason"], "批次已提交，不能重复提交。")
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
        self.assertEqual(withdrawn["status_bucket"], "withdrawn")
        self.assertFalse(withdrawn["can_submit"])
        self.assertFalse(withdrawn["can_withdraw"])
        self.assertEqual(withdrawn["blocked_reason"], "批次已撤回，不能提交。")
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

    def test_submitted_single_side_batch_prunes_rows_that_no_longer_match_category(self) -> None:
        rows = [
            bank_row("fee-1", category_code="fee", debit_amount="3.00"),
            bank_row("service-fee-1", category_code="fee", debit_amount="10000.00"),
        ]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="")
        changed_categories = {
            **categories_for([{**rows[0], "category_code": "fee"}]),
            "service-fee-1": {
                "transaction_id": "service-fee-1",
                "category_code": None,
                "category_label": None,
                "category_source": "",
            },
        }

        refreshed = self.assert_single_batch(
            service.build_batches(rows, changed_categories, pair_service.list_active_relations(), {}),
            "submitted",
        )

        self.assertEqual(refreshed["batch_id"], submitted["batch_id"])
        self.assertEqual(refreshed["row_ids"], ["fee-1"])
        self.assertEqual(refreshed["row_count"], 1)
        self.assertEqual(refreshed["total_amount"], "3.00")
        self.assertEqual(refreshed["tag_counts"], {"fee": 1})
        self.assertEqual(refreshed["version"], submitted["version"] + 1)
        relation = pair_service.get_active_relation_by_case_id(submitted["relation_case_id"])
        assert relation is not None
        self.assertEqual(relation["row_ids"], ["fee-1"])
        self.assertEqual(relation["special_metadata"]["row_count"], 1)
        self.assertEqual(relation["special_metadata"]["total_amount"], "3.00")
        self.assertNotIn("service-fee-1", service._active_no_oa_relation_row_ids(pair_service.list_active_relations()))
        migration_result = service.last_legacy_migration_result()
        self.assertTrue(migration_result["changed"])
        self.assertEqual(migration_result["affected_months"], ["2026-03"])

    def test_submitted_batch_that_becomes_stale_clears_active_relation(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="")
        changed_categories = categories_for([{**rows[0], "category_code": "salary"}])

        stale = self.assert_single_batch(
            service.build_batches(rows, changed_categories, pair_service.list_active_relations(), {}),
            "stale",
        )

        self.assertEqual(stale["batch_id"], submitted["batch_id"])
        self.assertEqual(stale["status_bucket"], "unsubmitted")
        self.assertFalse(stale["can_submit"])
        self.assertFalse(stale["can_withdraw"])
        self.assertEqual(stale["blocked_reason"], "源流水或分类已变化，需要复核后处理。")
        self.assertIsNone(pair_service.get_active_relation_by_case_id(submitted["relation_case_id"]))
        with self.assertRaisesRegex(ValueError, "stale_no_oa_bank_batch_has_no_active_relation_to_withdraw"):
            service.withdraw_batch(stale["batch_id"], actor="finance-user", expected_version=stale["version"], reason="源数据变化")

    def test_stale_without_active_no_oa_relation_is_not_withdrawable(self) -> None:
        rows = [bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WorkbenchPairRelationService()
        service = NoOaBankBatchService(pair_relation_service=pair_service)
        batch = self.assert_single_batch(service.build_batches(rows, categories_for(rows), [], {}), "draft")
        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="")
        changed_categories = categories_for([{**rows[0], "category_code": "salary"}])
        pair_service.cancel_relation(submitted["relation_case_id"])

        stale = self.assert_single_batch(service.build_batches(rows, changed_categories, [], {}), "stale")

        self.assertFalse(stale["can_withdraw"])
        with self.assertRaisesRegex(ValueError, "stale_no_oa_bank_batch_has_no_active_relation_to_withdraw"):
            service.withdraw_batch(stale["batch_id"], actor="finance-user", expected_version=stale["version"], reason="")

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
