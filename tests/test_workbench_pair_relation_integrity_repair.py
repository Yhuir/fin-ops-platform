from __future__ import annotations

import unittest

from fin_ops_platform.tools.repair_workbench_pair_relation_integrity import build_repair_plan


class WorkbenchPairRelationIntegrityRepairTests(unittest.TestCase):
    def test_repair_plan_replaces_stale_attachment_rows_with_current_sql_read_model_rows(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-1": {
                    "case_id": "case-1",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1", "bank-1", "oa-att-inv-oa-exp-1-old"],
                    "row_types": ["oa", "bank", "invoice"],
                    "special_metadata": {},
                }
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[
                {"row_id": "oa-exp-1", "source_kind": "oa"},
                {"row_id": "bank-1", "source_kind": "bank"},
                {"row_id": "oa-att-inv-oa-exp-1-new", "source_kind": "oa_attachment_invoice", "derived_from_oa_id": "oa-exp-1"},
            ],
            existing_oa_row_ids={"oa-exp-1"},
            actor_id="test",
        )

        relation = plan["snapshot"]["pair_relations"]["case-1"]
        self.assertEqual(plan["repaired_case_ids"], ["case-1"])
        self.assertEqual(relation["row_ids"], ["oa-exp-1", "bank-1", "oa-att-inv-oa-exp-1-new"])
        self.assertEqual(relation["row_types"], ["oa", "bank", "invoice"])
        self.assertEqual(plan["snapshot"]["pair_relation_history"][0]["operation_type"], "repair_relation_rows")

    def test_repair_plan_cancels_auto_offset_relation_when_oa_source_disappeared(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-stale": {
                    "case_id": "case-stale",
                    "status": "active",
                    "relation_mode": "oa_invoice_offset_auto_match",
                    "row_ids": ["oa-exp-missing", "oa-att-inv-oa-exp-missing-old"],
                    "row_types": ["oa", "invoice"],
                    "special_metadata": {},
                }
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[],
            existing_oa_row_ids=set(),
            actor_id="test",
        )

        relation = plan["snapshot"]["pair_relations"]["case-stale"]
        self.assertEqual(plan["cancelled_case_ids"], ["case-stale"])
        self.assertEqual(relation["status"], "cancelled")
        self.assertEqual(plan["snapshot"]["pair_relation_history"][0]["operation_type"], "repair_cancel_stale_relation")

    def test_repair_plan_adds_current_attachment_rows_when_relation_has_only_parent_oa(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-parent-only": {
                    "case_id": "case-parent-only",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                    "special_metadata": {},
                }
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[
                {"row_id": "oa-exp-1", "source_kind": "oa"},
                {"row_id": "bank-1", "source_kind": "bank"},
                {"row_id": "oa-att-inv-oa-exp-1-new", "source_kind": "oa_attachment_invoice", "derived_from_oa_id": "oa-exp-1"},
            ],
            existing_oa_row_ids={"oa-exp-1"},
            actor_id="test",
        )

        relation = plan["snapshot"]["pair_relations"]["case-parent-only"]
        self.assertEqual(plan["repaired_case_ids"], ["case-parent-only"])
        self.assertEqual(relation["row_ids"], ["oa-exp-1", "bank-1", "oa-att-inv-oa-exp-1-new"])

    def test_repair_plan_adds_item_attachment_rows_to_parent_oa_relation(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-parent-item": {
                    "case_id": "case-parent-item",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1968", "bank-1968"],
                    "row_types": ["oa", "bank"],
                    "special_metadata": {},
                }
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[
                {"row_id": "oa-exp-1968", "source_kind": "oa"},
                {"row_id": "bank-1968", "source_kind": "bank"},
                {
                    "row_id": "oa-att-inv-oa-exp-1968-item-4",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-exp-1968:item:4:de54f988bd66",
                },
            ],
            existing_oa_row_ids={"oa-exp-1968"},
            actor_id="test",
        )

        relation = plan["snapshot"]["pair_relations"]["case-parent-item"]
        self.assertEqual(plan["repaired_case_ids"], ["case-parent-item"])
        self.assertEqual(relation["row_ids"], ["oa-exp-1968", "bank-1968", "oa-att-inv-oa-exp-1968-item-4"])

    def test_repair_plan_removes_duplicate_row_ids_from_active_relation(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-duplicate-oa": {
                    "case_id": "case-duplicate-oa",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1", "bank-1", "oa-exp-1", "invoice-1"],
                    "row_types": ["oa", "bank", "oa", "invoice"],
                    "special_metadata": {},
                }
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[
                {"row_id": "oa-exp-1", "source_kind": "oa"},
                {"row_id": "bank-1", "source_kind": "bank"},
                {"row_id": "invoice-1", "source_kind": "invoice"},
            ],
            existing_oa_row_ids={"oa-exp-1"},
            actor_id="test",
        )

        relation = plan["snapshot"]["pair_relations"]["case-duplicate-oa"]
        self.assertEqual(plan["repaired_case_ids"], ["case-duplicate-oa"])
        self.assertEqual(plan["changed_case_ids"], ["case-duplicate-oa"])
        self.assertEqual(relation["row_ids"], ["oa-exp-1", "bank-1", "invoice-1"])
        self.assertEqual(relation["row_types"], ["oa", "bank", "invoice"])
        self.assertEqual(plan["snapshot"]["pair_relation_history"][0]["operation_type"], "repair_relation_rows")

    def test_repair_plan_only_changes_explicit_case_allowlist(self) -> None:
        snapshot = {
            "pair_relations": {
                "case-target": {
                    "case_id": "case-target",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1", "bank-1", "invoice-missing"],
                    "row_types": ["oa", "bank", "invoice"],
                    "special_metadata": {},
                },
                "case-out-of-scope": {
                    "case_id": "case-out-of-scope",
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-2", "bank-2", "invoice-missing-2"],
                    "row_types": ["oa", "bank", "invoice"],
                    "special_metadata": {},
                },
            },
            "pair_relation_history": [],
        }

        plan = build_repair_plan(
            snapshot,
            current_rows=[
                {"row_id": "oa-exp-1", "source_kind": "oa"},
                {"row_id": "bank-1", "source_kind": "bank"},
                {"row_id": "oa-exp-2", "source_kind": "oa"},
                {"row_id": "bank-2", "source_kind": "bank"},
            ],
            existing_oa_row_ids={"oa-exp-1", "oa-exp-2"},
            actor_id="test",
            case_ids=["case-target", "case-missing", "case-target"],
        )

        self.assertEqual(plan["requested_case_ids"], ["case-target", "case-missing"])
        self.assertEqual(plan["missing_requested_case_ids"], ["case-missing"])
        self.assertEqual(plan["changed_case_ids"], ["case-target"])
        self.assertEqual(
            plan["snapshot"]["pair_relations"]["case-out-of-scope"],
            snapshot["pair_relations"]["case-out-of-scope"],
        )


if __name__ == "__main__":
    unittest.main()
