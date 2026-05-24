from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_EXPIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_SUPPRESSED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WorkbenchDecision,
)


def decision(
    key: str,
    *,
    scope_month: str = "2026-05",
    status: str = DECISION_STATUS_PAIRED,
    row_ids: tuple[str, ...] = ("oa-1", "bank-1"),
    source_versions: dict[str, object] | None = None,
) -> WorkbenchDecision:
    return WorkbenchDecision(
        decision_id=key,
        decision_key=key,
        scope_month=scope_month,
        display_state=DISPLAY_STATE_PAIRED if status == DECISION_STATUS_PAIRED else DISPLAY_STATE_OPEN,
        decision_status=status,
        match_domain=MATCH_DOMAIN_FREE,
        match_shape="oa_bank",
        rule_code="free.oa_bank",
        rule_version="v1",
        row_ids=row_ids,
        oa_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("oa-")),
        bank_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("bank-")),
        invoice_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("invoice-")),
        amount="100.00",
        direction="expense",
        payment_amount_closed=True,
        invoice_amount_closed=False,
        source_versions=source_versions or {"oa": 1, "bank": 1},
    )


class WorkbenchReconciliationDecisionStoreTests(unittest.TestCase):
    def test_upsert_is_idempotent_by_decision_key_and_list_filters_by_scope_status(self) -> None:
        store = WorkbenchReconciliationDecisionStore()

        store.upsert_decisions([decision("decision-a", status=DECISION_STATUS_PAIRED)])
        store.upsert_decisions([decision("decision-a", status=DECISION_STATUS_OPEN, row_ids=("oa-2",))])
        store.upsert_decisions([decision("decision-b", scope_month="2026-06", status=DECISION_STATUS_PAIRED)])

        self.assertEqual(
            [item["decision_key"] for item in store.list_decisions("2026-05")],
            ["decision-a"],
        )
        self.assertEqual(
            store.list_decisions("2026-05", statuses={DECISION_STATUS_PAIRED}),
            [],
        )
        open_rows = store.list_decisions("2026-05", statuses={DECISION_STATUS_OPEN})
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0]["row_ids"], ["oa-2"])

    def test_consume_and_suppress_by_row_ids_update_overlapping_active_decisions(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        store.upsert_decisions(
            [
                decision("decision-a", row_ids=("oa-1", "bank-1")),
                decision("decision-b", row_ids=("oa-2", "bank-2")),
                decision("decision-c", status=DECISION_STATUS_OPEN, row_ids=("oa-3",)),
            ]
        )

        self.assertEqual(store.consume_by_row_ids(["bank-1", "missing"], relation_id="relation-1"), 1)
        self.assertEqual(store.suppress_by_row_ids(["oa-3"], exception_case_id="exception-1"), 1)

        rows = {item["decision_key"]: item for item in store.list_decisions("2026-05")}
        self.assertEqual(rows["decision-a"]["decision_status"], DECISION_STATUS_CONSUMED)
        self.assertEqual(rows["decision-a"]["consumed_by_relation_id"], "relation-1")
        self.assertEqual(rows["decision-c"]["decision_status"], DECISION_STATUS_SUPPRESSED)
        self.assertEqual(rows["decision-c"]["suppressed_by_exception_case_id"], "exception-1")
        self.assertEqual(rows["decision-b"]["decision_status"], DECISION_STATUS_PAIRED)

    def test_expire_stale_source_versions_only_marks_changed_scope_decisions(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        store.upsert_decisions(
            [
                decision("stale", source_versions={"oa": 1, "bank": 1}),
                decision("fresh", row_ids=("oa-2",), source_versions={"oa": 2, "bank": 1}),
                decision("other-month", scope_month="2026-06", source_versions={"oa": 1}),
            ]
        )

        self.assertEqual(store.expire_stale(["2026-05"], source_versions={"oa": 2, "bank": 1}), 1)

        rows = {item["decision_key"]: item for item in store.list_decisions("2026-05")}
        self.assertEqual(rows["stale"]["decision_status"], DECISION_STATUS_EXPIRED)
        self.assertEqual(rows["fresh"]["decision_status"], DECISION_STATUS_PAIRED)


if __name__ == "__main__":
    unittest.main()
