from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_reconciliation_decision_cleanup import (
    WorkbenchReconciliationDecisionCleanupService,
)


class FakeCleanupRepository:
    def __init__(self, decisions: list[dict[str, object]]) -> None:
        self.decisions = list(decisions)
        self.expire_calls: list[dict[str, object]] = []

    def list_active_workbench_reconciliation_decisions_for_cleanup(
        self,
        *,
        tenant_id: str,
        scope_months: list[str] | None = None,
        decision_keys: list[str] | None = None,
    ) -> list[dict[str, object]]:
        return list(self.decisions)

    def expire_workbench_reconciliation_decisions_by_keys(
        self,
        *,
        tenant_id: str,
        decision_keys: list[str],
        reason: str,
        actor: str = "repair_workbench_reconciliation_decisions",
    ) -> dict[str, object]:
        self.expire_calls.append(
            {
                "tenant_id": tenant_id,
                "decision_keys": list(decision_keys),
                "reason": reason,
                "actor": actor,
            }
        )
        return {"expired_count": len(decision_keys), "scope_keys": ["2026-02"]}


class WorkbenchReconciliationDecisionCleanupServiceTests(unittest.TestCase):
    def test_plan_expires_decisions_overlapping_active_relations(self) -> None:
        repository = FakeCleanupRepository(
            [
                {
                    "decision_key": "decision:2026-02:oa_bank_exact_sum:oa-pay-2050:txn_imported_1385",
                    "scope_month": "2026-02",
                    "decision_status": "paired",
                    "rule_code": "oa_bank_exact_sum",
                    "row_ids": ["oa-pay-2050", "txn_imported_1385"],
                    "oa_row_ids": ["oa-pay-2050"],
                    "bank_row_ids": ["txn_imported_1385"],
                    "invoice_row_ids": [],
                    "evidence": {},
                    "active_relation_overlaps": [
                        {
                            "case_id": "no_oa_batch_b1a825c98bf5d29b67f0",
                            "relation_mode": "no_oa_bank_batch",
                            "month_scope": "2026-03",
                            "overlap_row_ids": ["txn_imported_1385"],
                        }
                    ],
                }
            ]
        )

        plan = WorkbenchReconciliationDecisionCleanupService(repository=repository).build_plan(scope_months=["2026-02"])

        self.assertEqual(plan["invalid_decision_count"], 1)
        self.assertEqual(plan["affected_scope_keys"], ["2026-02"])
        self.assertEqual(plan["recommended_rebuild_scopes"], ["2026-02", "all"])
        self.assertEqual(plan["items"][0]["planned_action"], "expire")
        self.assertEqual(plan["items"][0]["reasons"][0]["code"], "active_relation_row_overlap")

    def test_plan_expires_oa_bank_exact_sum_with_only_weak_generic_token(self) -> None:
        repository = FakeCleanupRepository(
            [
                {
                    "decision_key": "decision:2026-02:oa_bank_exact_sum:oa-pay-2050:txn_imported_1286:txn_imported_1378",
                    "scope_month": "2026-02",
                    "decision_status": "paired",
                    "rule_code": "oa_bank_exact_sum",
                    "row_ids": ["oa-pay-2050", "txn_imported_1286", "txn_imported_1378"],
                    "oa_row_ids": ["oa-pay-2050"],
                    "bank_row_ids": ["txn_imported_1286", "txn_imported_1378"],
                    "invoice_row_ids": [],
                    "evidence": {
                        "oa_bank_text_matches": [
                            {
                                "bank_row_id": "txn_imported_1286",
                                "matches": [{"token": "科技", "left_source_field": "project", "right_source_field": "counterparty"}],
                            },
                            {
                                "bank_row_id": "txn_imported_1378",
                                "matches": [{"token": "科技", "left_source_field": "project", "right_source_field": "counterparty"}],
                            },
                        ]
                    },
                    "active_relation_overlaps": [],
                }
            ]
        )

        plan = WorkbenchReconciliationDecisionCleanupService(repository=repository).build_plan()

        self.assertEqual(plan["invalid_decision_count"], 1)
        self.assertEqual(plan["items"][0]["reasons"][0]["code"], "weak_only_oa_bank_sum_evidence")

    def test_plan_expires_oa_bank_exact_sum_with_project_name_only_token(self) -> None:
        repository = FakeCleanupRepository(
            [
                {
                    "decision_key": "decision:2026-02:oa_bank_exact_sum:oa-pay-2050:txn_imported_1385:txn_imported_1414",
                    "scope_month": "2026-02",
                    "decision_status": "paired",
                    "rule_code": "oa_bank_exact_sum",
                    "row_ids": ["oa-pay-2050", "txn_imported_1385", "txn_imported_1414"],
                    "oa_row_ids": ["oa-pay-2050"],
                    "bank_row_ids": ["txn_imported_1385", "txn_imported_1414"],
                    "invoice_row_ids": [],
                    "evidence": {
                        "oa_bank_text_matches": [
                            {
                                "bank_row_id": "txn_imported_1385",
                                "matches": [
                                    {
                                        "token": "云南溯源科技",
                                        "left_source_field": "oa.project",
                                        "right_source_field": "bank.counterparty",
                                    }
                                ],
                            },
                            {
                                "bank_row_id": "txn_imported_1414",
                                "matches": [
                                    {
                                        "token": "云南溯源科技",
                                        "left_source_field": "oa.project",
                                        "right_source_field": "bank.counterparty",
                                    }
                                ],
                            },
                        ]
                    },
                    "active_relation_overlaps": [],
                }
            ]
        )

        plan = WorkbenchReconciliationDecisionCleanupService(repository=repository).build_plan()

        self.assertEqual(plan["invalid_decision_count"], 1)
        self.assertEqual(plan["items"][0]["reasons"][0]["code"], "weak_only_oa_bank_sum_evidence")

    def test_plan_expires_decisions_overlapping_submitted_no_oa_batches(self) -> None:
        repository = FakeCleanupRepository(
            [
                {
                    "decision_key": "decision:2026-02:oa_bank_exact_sum:oa-pay-2050:txn_imported_1385",
                    "scope_month": "2026-02",
                    "decision_status": "paired",
                    "rule_code": "oa_bank_exact_sum",
                    "row_ids": ["oa-pay-2050", "txn_imported_1385"],
                    "oa_row_ids": ["oa-pay-2050"],
                    "bank_row_ids": ["txn_imported_1385"],
                    "invoice_row_ids": [],
                    "evidence": {},
                    "active_relation_overlaps": [],
                    "submitted_no_oa_batch_overlaps": [
                        {
                            "batch_id": "no_oa_batch_b1a825c98bf5d29b67f0",
                            "batch_type": "internal_transfer",
                            "status": "submitted",
                            "scope_month": "2026-03",
                            "overlap_row_ids": ["txn_imported_1385"],
                        }
                    ],
                }
            ]
        )

        plan = WorkbenchReconciliationDecisionCleanupService(repository=repository).build_plan(scope_months=["2026-02"])

        self.assertEqual(plan["invalid_decision_count"], 1)
        self.assertEqual(plan["items"][0]["reasons"][0]["code"], "submitted_no_oa_batch_row_overlap")

    def test_execute_expires_only_planned_invalid_decisions(self) -> None:
        repository = FakeCleanupRepository(
            [
                {
                    "decision_key": "bad-decision",
                    "scope_month": "2026-02",
                    "decision_status": "paired",
                    "rule_code": "oa_bank_exact_sum",
                    "row_ids": ["oa-1", "bank-1"],
                    "evidence": {},
                    "active_relation_overlaps": [{"case_id": "active-case", "overlap_row_ids": ["bank-1"]}],
                }
            ]
        )
        service = WorkbenchReconciliationDecisionCleanupService(repository=repository, tenant_id="tenant-a")
        plan = service.build_plan()

        execution = service.execute_plan(plan, reason="unit-test")

        self.assertEqual(execution["expired_count"], 1)
        self.assertEqual(repository.expire_calls[0]["tenant_id"], "tenant-a")
        self.assertEqual(repository.expire_calls[0]["decision_keys"], ["bad-decision"])
        self.assertEqual(repository.expire_calls[0]["reason"], "unit-test")


if __name__ == "__main__":
    unittest.main()
