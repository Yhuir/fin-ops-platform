from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_pair_relation_display_policy import (
    WorkbenchPairRelationDisplayPolicy,
)


class WorkbenchPairRelationDisplayPolicyTests(unittest.TestCase):
    def _policy(self) -> WorkbenchPairRelationDisplayPolicy:
        return WorkbenchPairRelationDisplayPolicy(
            no_oa_relation_display_payload=lambda metadata: {
                "code": "no_oa_bank_batch",
                "label": f"no-oa:{(metadata or {}).get('batch_label', '')}",
                "tone": "success",
            },
            bank_transaction_tag_label=lambda code: "工资" if code == "salary" else code,
            no_oa_bank_batch_relation_mode="no_oa_bank_batch",
            personal_advance_repayment_mode="personal_advance_repayment",
            oa_invoice_offset_auto_match_mode="oa_invoice_offset_auto_match",
        )

    def test_no_oa_relation_display_delegates_to_policy_port(self) -> None:
        payload = self._policy().display_payload(
            relation_mode="no_oa_bank_batch",
            special_metadata={"batch_label": "批次A"},
        )

        self.assertEqual(payload, {"code": "no_oa_bank_batch", "label": "no-oa:批次A", "tone": "success"})

    def test_known_relation_modes_return_expected_labels(self) -> None:
        policy = self._policy()

        self.assertEqual(
            policy.display_payload(relation_mode="internal_transfer_pair"),
            {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"},
        )
        self.assertEqual(
            policy.display_payload(relation_mode="salary_personal_auto_match"),
            {"code": "salary_personal_auto_match", "label": "已匹配：工资", "tone": "success"},
        )
        self.assertEqual(
            policy.display_payload(relation_mode="personal_advance_repayment"),
            {"code": "personal_advance_repayment", "label": "已匹配：还清个人暂借款", "tone": "success"},
        )
        self.assertEqual(
            policy.display_payload(relation_mode="turnover_manual_closure"),
            {"code": "turnover_manual_closure", "label": "外部往来款闭环", "tone": "success"},
        )

    def test_oa_invoice_offset_label_depends_on_row_type(self) -> None:
        policy = self._policy()

        self.assertEqual(
            policy.display_payload(relation_mode="oa_invoice_offset_auto_match", row_type="invoice"),
            {"code": "oa_invoice_offset_auto_match", "label": "已关联OA", "tone": "success"},
        )
        self.assertEqual(
            policy.display_payload(relation_mode="oa_invoice_offset_auto_match", row_type="oa"),
            {"code": "oa_invoice_offset_auto_match", "label": "待找流水与发票", "tone": "warn"},
        )

    def test_unknown_relation_mode_defaults_to_fully_linked(self) -> None:
        self.assertEqual(
            self._policy().display_payload(relation_mode="manual_confirmed"),
            {"code": "fully_linked", "label": "完全关联", "tone": "success"},
        )


if __name__ == "__main__":
    unittest.main()
