from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
import unittest

from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_EXPIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_PROPOSED,
    DECISION_STATUS_SUPPRESSED,
    DECISION_STATUSES,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    DISPLAY_STATES,
    MATCH_DOMAIN_FREE,
    MATCH_DOMAIN_SPECIAL,
    MATCH_DOMAINS,
    WARNING_INVOICE_AMOUNT_MISMATCH,
    DecisionWarning,
    WorkbenchReconciliationDecision,
    expand_scope_month_window,
    resolve_decision_scope_month,
)


class WorkbenchReconciliationModelTests(unittest.TestCase):
    def test_display_states_are_only_paired_and_open(self) -> None:
        self.assertEqual(DISPLAY_STATE_PAIRED, "paired")
        self.assertEqual(DISPLAY_STATE_OPEN, "open")
        self.assertEqual(DISPLAY_STATES, ("paired", "open"))

    def test_decision_statuses_are_exact_contract_values(self) -> None:
        self.assertEqual(DECISION_STATUS_PROPOSED, "proposed")
        self.assertEqual(DECISION_STATUS_PAIRED, "paired")
        self.assertEqual(DECISION_STATUS_OPEN, "open")
        self.assertEqual(DECISION_STATUS_SUPPRESSED, "suppressed")
        self.assertEqual(DECISION_STATUS_CONSUMED, "consumed")
        self.assertEqual(DECISION_STATUS_EXPIRED, "expired")
        self.assertEqual(
            DECISION_STATUSES,
            ("proposed", "paired", "open", "suppressed", "consumed", "expired"),
        )

    def test_match_domains_are_only_free_and_special(self) -> None:
        self.assertEqual(MATCH_DOMAIN_FREE, "free")
        self.assertEqual(MATCH_DOMAIN_SPECIAL, "special")
        self.assertEqual(MATCH_DOMAINS, ("free", "special"))

    def test_invoice_amount_mismatch_warning_code_exists(self) -> None:
        warning = DecisionWarning(
            code=WARNING_INVOICE_AMOUNT_MISMATCH,
            message="OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。",
        )

        self.assertEqual(WARNING_INVOICE_AMOUNT_MISMATCH, "invoice_amount_mismatch")
        self.assertEqual(
            warning.to_dict(),
            {
                "code": "invoice_amount_mismatch",
                "message": "OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。",
            },
        )

    def test_bank_containing_decisions_use_bank_trade_month_as_scope_month(self) -> None:
        self.assertEqual(
            resolve_decision_scope_month(
                has_bank=True,
                bank_trade_month="2026-03",
                has_oa=True,
                oa_month="2026-02",
            ),
            "2026-03",
        )

    def test_oa_invoice_decisions_without_bank_use_oa_month_as_scope_month(self) -> None:
        self.assertEqual(
            resolve_decision_scope_month(
                has_bank=False,
                bank_trade_month=None,
                has_oa=True,
                oa_month="2026-04",
            ),
            "2026-04",
        )

    def test_scope_month_resolution_rejects_missing_ownership_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "bank_trade_month"):
            resolve_decision_scope_month(
                has_bank=True,
                bank_trade_month=None,
                has_oa=True,
                oa_month="2026-02",
            )

        with self.assertRaisesRegex(ValueError, "oa_month"):
            resolve_decision_scope_month(
                has_bank=False,
                bank_trade_month=None,
                has_oa=True,
                oa_month=None,
            )

    def test_month_expansion_returns_five_calendar_months(self) -> None:
        self.assertEqual(
            expand_scope_month_window("2026-01"),
            ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"],
        )

    def test_model_serializes_to_plain_repository_dictionary(self) -> None:
        decision = WorkbenchReconciliationDecision(
            decision_id="decision:2026-03:oa_attachment_invoice_with_bank:abc",
            decision_key="decision:2026-03:oa_attachment_invoice_with_bank:abc",
            scope_month="2026-03",
            display_state=DISPLAY_STATE_PAIRED,
            decision_status=DECISION_STATUS_PAIRED,
            match_domain=MATCH_DOMAIN_FREE,
            match_shape="oa_bank_invoice",
            rule_code="oa_attachment_invoice_with_bank",
            rule_version="2026-05-25",
            row_ids=("oa-exp-1994", "bk-o-1", "oa-att-inv-1"),
            oa_row_ids=("oa-exp-1994",),
            bank_row_ids=("bk-o-1",),
            invoice_row_ids=("oa-att-inv-1",),
            amount=Decimal("6000.00"),
            direction="expenditure",
            payment_amount_closed=True,
            invoice_amount_closed=False,
            warnings=(
                DecisionWarning(
                    code=WARNING_INVOICE_AMOUNT_MISMATCH,
                    message="OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。",
                ),
            ),
            evidence={"scope_window": expand_scope_month_window("2026-03")},
            blockers=(),
            explanation="OA、流水金额闭合，OA 来源附件发票合计不一致。",
            generated_at=datetime(2026, 5, 7, 10, 0, tzinfo=UTC),
            source_versions={"workbench_read_model_schema_version": "2026-05-07-invoice-etc-unified-identity"},
        )

        payload = decision.to_dict()

        self.assertEqual(payload["amount"], "6000.00")
        self.assertEqual(payload["generated_at"], "2026-05-07T10:00:00+00:00")
        self.assertEqual(payload["row_ids"], ["oa-exp-1994", "bk-o-1", "oa-att-inv-1"])
        self.assertEqual(
            payload["warnings"],
            [
                {
                    "code": "invoice_amount_mismatch",
                    "message": "OA 与流水金额一致，但 OA 来源附件发票合计金额不一致。",
                }
            ],
        )
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
