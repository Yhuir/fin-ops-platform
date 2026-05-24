from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_engine import WorkbenchReconciliationEngine
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_EXPIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_SPECIAL,
    WorkbenchDecision,
)
from fin_ops_platform.services.workbench_special_reconciliation_adapter import WorkbenchSpecialReconciliationResult


class WorkbenchReconciliationEngineTests(unittest.TestCase):
    def test_manual_relation_rows_are_excluded_before_matching(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-held",
            row_ids=["oa-held", "bank-held"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-05",
        )

        summary = WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=pair_service,
        ).run_scope(
            "2026-05",
            oa_rows=[oa_row("oa-held"), oa_row("oa-free")],
            bank_rows=[bank_row("bank-held"), bank_row("bank-free")],
            invoice_rows=[],
            source_versions={"engine": "v2"},
        )

        decisions = store.list_decisions("2026-05")
        self.assertEqual(summary["suppressed_by_pair_relation_count"], 2)
        self.assertEqual([decision["row_ids"] for decision in decisions], [["oa-free", "bank-free"]])

    def test_special_decisions_claim_rows_before_free_matching(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        special_decision = special_pair("2026-05", ["oa-1", "bank-1"])

        WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=WorkbenchPairRelationService(),
            special_adapter=StaticSpecialAdapter([special_decision]),
        ).run_scope(
            "2026-05",
            oa_rows=[oa_row("oa-1")],
            bank_rows=[bank_row("bank-1")],
            invoice_rows=[],
            source_versions={"engine": "v2"},
        )

        decisions = store.list_decisions("2026-05")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["match_domain"], MATCH_DOMAIN_SPECIAL)
        self.assertEqual(decisions[0]["row_ids"], ["oa-1", "bank-1"])

    def test_free_matching_sees_full_t_minus_2_to_t_plus_2_window(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        engine = WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=WorkbenchPairRelationService(),
        )

        engine.run_scope(
            "2026-06",
            oa_rows=[oa_row("oa-may", month="2026-05")],
            bank_rows=[bank_row("bank-june", month="2026-06")],
            invoice_rows=[],
            source_versions={"engine": "v2"},
        )

        decisions = store.list_decisions("2026-06")
        self.assertEqual([decision["row_ids"] for decision in decisions], [["oa-may", "bank-june"]])
        self.assertEqual(decisions[0]["evidence"]["scope_window"], ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08"])

    def test_decisions_persist_only_to_primary_scope_month(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        engine = WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=WorkbenchPairRelationService(),
        )

        engine.run_scope(
            "2026-05",
            oa_rows=[oa_row("oa-may", month="2026-05")],
            bank_rows=[bank_row("bank-june", month="2026-06")],
            invoice_rows=[],
            source_versions={"engine": "v2"},
        )

        self.assertEqual(store.list_decisions("2026-05"), [])
        self.assertEqual(store.list_decisions("2026-06"), [])

    def test_stale_source_version_decisions_expire_before_upsert(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        old_decision = special_pair("2026-05", ["oa-old", "bank-old"], source_versions={"engine": "v1"})
        store.upsert_decisions([old_decision])

        summary = WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=WorkbenchPairRelationService(),
        ).run_scope(
            "2026-05",
            oa_rows=[oa_row("oa-new")],
            bank_rows=[bank_row("bank-new")],
            invoice_rows=[],
            source_versions={"engine": "v2"},
        )

        decisions = store.list_decisions("2026-05", statuses={DECISION_STATUS_EXPIRED, DECISION_STATUS_PAIRED})
        self.assertEqual(summary["expired_decision_count"], 1)
        self.assertEqual({decision["decision_status"] for decision in decisions}, {DECISION_STATUS_EXPIRED, DECISION_STATUS_PAIRED})

    def test_conflicting_free_rows_become_open_decisions_not_paired(self) -> None:
        store = WorkbenchReconciliationDecisionStore()

        WorkbenchReconciliationEngine(
            decision_store=store,
            pair_relation_service=WorkbenchPairRelationService(),
        ).run_scope(
            "2026-05",
            oa_rows=[oa_row("oa-1")],
            bank_rows=[bank_row("bank-1")],
            invoice_rows=[
                invoice_row("invoice-1", seller_name="供应商"),
                invoice_row("invoice-2", seller_name="供应商"),
            ],
            source_versions={"engine": "v2"},
        )

        decisions = store.list_decisions("2026-05")
        self.assertTrue(decisions)
        self.assertEqual({decision["decision_status"] for decision in decisions}, {DECISION_STATUS_OPEN})
        self.assertEqual({decision["display_state"] for decision in decisions}, {"open"})


class StaticSpecialAdapter:
    def __init__(self, decisions: list[WorkbenchDecision]) -> None:
        self.decisions = tuple(decisions)

    def generate_decisions(self, *args, **kwargs) -> WorkbenchSpecialReconciliationResult:
        claimed = {row_id for decision in self.decisions for row_id in decision.row_ids}
        return WorkbenchSpecialReconciliationResult(
            decisions=self.decisions,
            claimed_row_ids_by_domain={MATCH_DOMAIN_SPECIAL: claimed},
        )


def oa_row(row_id: str, *, month: str = "2026-05", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "month": month,
        "amount": amount,
        "applicant": "张三",
        "project_name": "项目A",
        "reason": "支付供应商",
    }


def bank_row(row_id: str, *, month: str = "2026-05", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "month": month,
        "debit_amount": amount,
        "credit_amount": "",
        "counterparty_name": "供应商",
        "summary": "支付供应商",
    }


def invoice_row(row_id: str, *, month: str = "2026-05", seller_name: str = "供应商", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "month": month,
        "invoice_date": f"{month}-10",
        "total_with_tax": amount,
        "invoice_type": "进项发票",
        "seller_name": seller_name,
    }


def special_pair(
    scope_month: str,
    row_ids: list[str],
    *,
    source_versions: dict[str, object] | None = None,
) -> WorkbenchDecision:
    return WorkbenchDecision(
        decision_id=f"special:{scope_month}:{':'.join(row_ids)}",
        decision_key=f"special:{scope_month}:{':'.join(row_ids)}",
        scope_month=scope_month,
        display_state=DISPLAY_STATE_PAIRED,
        decision_status=DECISION_STATUS_PAIRED,
        match_domain=MATCH_DOMAIN_SPECIAL,
        match_shape="oa_bank",
        rule_code="special_test_rule",
        rule_version="test",
        row_ids=tuple(row_ids),
        oa_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("oa")),
        bank_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("bank")),
        amount=Decimal("100.00"),
        direction="expenditure",
        payment_amount_closed=True,
        invoice_amount_closed=None,
        source_versions=source_versions or {},
    )


if __name__ == "__main__":
    unittest.main()
