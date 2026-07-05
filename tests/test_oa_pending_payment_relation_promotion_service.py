from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_pending_payment_relation_promotion_service import (
    OaPendingPaymentRelationPromotionService,
)


class OaPendingPaymentRelationPromotionServiceTests(unittest.TestCase):
    def test_promotes_pending_relation_when_all_oa_rows_are_completed(self) -> None:
        pending = FakePendingRelationService(
            [
                {
                    "relation_id": "pending-oa-bank",
                    "status": "active",
                    "month_scope": "2026-02",
                    "oa_row_ids": ["oa-completed"],
                    "bank_transaction_ids": ["bank-paid"],
                    "source_action": "link_bank_transactions",
                    "amount_check": {"matched": True},
                    "migrated_from_workbench_case_id": "legacy-case-id",
                }
            ]
        )
        relation_command = FakeWorkbenchRelationCommandService()
        service = OaPendingPaymentRelationPromotionService(
            pending_relation_service=pending,
            relation_command_service=relation_command,
        )

        result = service.promote_completed_records([_oa("oa-completed", "2026-02")])

        self.assertEqual(result["promoted_count"], 1)
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["affected_months"], ["2026-02"])
        self.assertEqual(pending.promoted_calls, [("pending-oa-bank", "legacy-case-id", "oa_projection_sync")])
        confirm = relation_command.confirm_calls[0]
        self.assertEqual(confirm["case_id"], "legacy-case-id")
        self.assertEqual(confirm["row_ids"], ["oa-completed", "bank-paid"])
        self.assertEqual(confirm["row_types"], ["oa", "bank"])
        self.assertEqual(confirm["relation_mode"], "manual_confirmed")
        self.assertEqual(confirm["month_scope"], "2026-02")
        self.assertEqual(confirm["special_metadata"]["origin"], "oa_pending_payment_promotion")
        self.assertEqual(confirm["special_metadata"]["pending_relation_id"], "pending-oa-bank")

    def test_skips_relation_until_all_oa_rows_are_completed(self) -> None:
        pending = FakePendingRelationService(
            [
                {
                    "relation_id": "pending-multi-oa",
                    "status": "active",
                    "month_scope": "2026-02",
                    "oa_row_ids": ["oa-completed", "oa-still-progress"],
                    "bank_transaction_ids": ["bank-paid"],
                }
            ]
        )
        relation_command = FakeWorkbenchRelationCommandService()
        service = OaPendingPaymentRelationPromotionService(
            pending_relation_service=pending,
            relation_command_service=relation_command,
        )

        result = service.promote_completed_records([_oa("oa-completed", "2026-02")])

        self.assertEqual(result["promoted_count"], 0)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(relation_command.confirm_calls, [])
        self.assertEqual(pending.promoted_calls, [])


class FakePendingRelationService:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self.relations = [dict(relation) for relation in relations]
        self.promoted_calls: list[tuple[str, str, str]] = []

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        wanted = {str(row_id) for row_id in row_ids}
        return [
            dict(relation)
            for relation in self.relations
            if wanted & {str(row_id) for row_id in list(relation.get("oa_row_ids") or [])}
        ]

    def mark_relation_promoted(self, *, relation_id: str, workbench_case_id: str, actor_id: str) -> dict[str, object]:
        self.promoted_calls.append((relation_id, workbench_case_id, actor_id))
        for relation in self.relations:
            if relation.get("relation_id") == relation_id:
                relation["status"] = "promoted"
                return {
                    "status": "promoted",
                    "relation": dict(relation),
                    "affected_months": [str(relation.get("month_scope") or "all")],
                }
        return {"status": "promoted", "affected_months": []}


class FakeWorkbenchRelationCommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        return {"status": "confirmed", "relation": {"case_id": kwargs.get("case_id")}}


def _oa(row_id: str, month: str) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="open",
        case_id=None,
        applicant="测试申请人",
        project_name="测试项目",
        apply_type="支付申请",
        amount="100.00",
        counterparty_name="测试供应商",
        reason="测试付款",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status="completed",
    )


if __name__ == "__main__":
    unittest.main()
