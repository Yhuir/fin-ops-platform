from __future__ import annotations

import unittest

from fin_ops_platform.services.no_oa_bank_batch_workbench_payload_decorator import (
    NoOaBankBatchWorkbenchPayloadDecorator,
)


class NoOaBankBatchWorkbenchPayloadDecoratorTests(unittest.TestCase):
    def test_relation_with_batch_metadata_enriches_source_batch_fields(self) -> None:
        decorator = NoOaBankBatchWorkbenchPayloadDecorator(
            batch_provider=lambda batch_id: {
                "id": batch_id,
                "version": 7,
                "batch_type": "fee",
                "batch_label": "手续费",
                "row_count": 2,
                "total_amount": "88.00",
                "can_withdraw": True,
            }
        )

        relation = decorator.relation_with_batch_metadata(
            {"special_metadata": {"source_batch_id": "batch-001", "cost_policy": "exclude_all"}}
        )

        self.assertEqual(
            relation["special_metadata"],
            {
                "source_batch_id": "batch-001",
                "cost_policy": "exclude_all",
                "batch_version": 7,
                "batch_type": "fee",
                "batch_label": "手续费",
                "row_count": 2,
                "total_amount": "88.00",
                "withdrawable": True,
            },
        )

    def test_apply_pair_metadata_preserves_tags_cost_and_batch_fields(self) -> None:
        payload: dict[str, object] = {
            "tags": ["银行流水"],
            "summary_fields": {},
            "detail_fields": {},
        }
        relation = {
            "special_metadata": {
                "source_batch_id": "batch-001",
                "batch_label": "手续费",
                "cost_policy": "exclude_all",
            },
            "display_tags": ["免OA", "手续费"],
        }

        NoOaBankBatchWorkbenchPayloadDecorator.apply_pair_metadata(payload, relation)

        self.assertEqual(payload["tags"], ["银行流水", "免OA", "手续费"])
        self.assertEqual(payload["display_tags"], ["免OA", "手续费"])
        self.assertTrue(payload["cost_excluded"])
        self.assertEqual(payload["summary_fields"], {"免OA批次": "手续费", "成本统计": "不计入"})
        self.assertEqual(payload["detail_fields"], {"免OA批次": "手续费", "成本统计": "不计入"})

    def test_apply_available_actions_respects_withdrawable_metadata(self) -> None:
        payload: dict[str, object] = {
            "special_metadata": {"source_batch_id": "batch-001", "withdrawable": True},
            "available_actions": [],
        }

        NoOaBankBatchWorkbenchPayloadDecorator.apply_available_actions(payload)

        self.assertEqual(payload["available_actions"], ["detail", "withdraw_no_oa_batch"])

    def test_apply_available_actions_skips_non_withdrawable_batch(self) -> None:
        payload: dict[str, object] = {
            "special_metadata": {"source_batch_id": "batch-001", "withdrawable": False},
            "available_actions": ["detail"],
        }

        NoOaBankBatchWorkbenchPayloadDecorator.apply_available_actions(payload)

        self.assertEqual(payload["available_actions"], ["detail"])


if __name__ == "__main__":
    unittest.main()
