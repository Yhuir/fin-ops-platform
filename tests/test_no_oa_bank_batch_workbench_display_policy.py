from __future__ import annotations

import unittest

from fin_ops_platform.services.no_oa_bank_batch_workbench_display_policy import (
    NoOaBankBatchWorkbenchDisplayPolicy,
)


class NoOaBankBatchWorkbenchDisplayPolicyTests(unittest.TestCase):
    def test_relation_display_payload_uses_batch_label_when_present(self) -> None:
        policy = NoOaBankBatchWorkbenchDisplayPolicy(label_provider=lambda code: code)

        payload = policy.relation_display_payload({"batch_label": "手续费"})

        self.assertEqual(
            payload,
            {"code": "no_oa_bank_batch", "label": "已匹配：手续费", "tone": "success"},
        )

    def test_relation_display_payload_falls_back_to_no_oa_label(self) -> None:
        policy = NoOaBankBatchWorkbenchDisplayPolicy(label_provider=lambda code: code)

        payload = policy.relation_display_payload({})

        self.assertEqual(
            payload,
            {"code": "no_oa_bank_batch", "label": "已匹配：免OA流水", "tone": "success"},
        )

    def test_row_tags_merges_display_sources_and_filters_managed_labels(self) -> None:
        policy = NoOaBankBatchWorkbenchDisplayPolicy(
            label_provider=lambda code: {"fee": "手续费", "salary": "工资"}.get(code, code)
        )

        tags = policy.row_tags(
            relation={"display_tags": ["工资", "自定义关系"]},
            group={"display_tags": ["手续费", "分组标签"]},
            special_metadata={
                "display_tags": ["内部往来款", "元数据标签"],
                "batch_type": "fee",
                "batch_label": "手续费",
            },
        )

        self.assertEqual(tags, ["自定义关系", "分组标签", "元数据标签", "手续费"])


if __name__ == "__main__":
    unittest.main()
