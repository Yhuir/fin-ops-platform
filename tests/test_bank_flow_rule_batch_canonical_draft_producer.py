from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_flow_rule_batch_canonical_draft_producer import (
    BankFlowRuleBatchCanonicalDraftProducer,
)


class RecordingQueueRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        scope_type: str,
        scope_key: str,
        dedupe_key: str,
        payload: dict[str, object],
    ) -> object:
        self.calls.append(dict(locals()) | {"self": None})
        self.calls[-1].pop("self", None)
        return type(
            "Event",
            (),
            {
                "event_id": f"job:{scope_key}",
                "dedupe_key": dedupe_key,
            },
        )()


class BankFlowRuleBatchCanonicalDraftProducerTests(unittest.TestCase):
    def test_enqueue_normalizes_scope_keys_and_uses_canonical_draft_event(self) -> None:
        queue = RecordingQueueRepository()
        producer = BankFlowRuleBatchCanonicalDraftProducer(
            queue_repository_provider=lambda: queue
        )

        jobs = producer.enqueue_scope_keys(
            [" 2026-05 ", "", "bad", "all", "2026-05"],
            reason="unit_test",
            metadata={"source": "test"},
        )

        self.assertEqual(jobs, ["job:2026-05", "job:all"])
        self.assertEqual(
            queue.calls,
            [
                {
                    "event_type": "bank_flow_rule_batch.canonical_draft.refresh",
                    "aggregate_type": "bank_flow_rule_batch",
                    "aggregate_id": "2026-05",
                    "scope_type": "bank_flow_rule_batch_draft",
                    "scope_key": "2026-05",
                    "dedupe_key": (
                        "bank_flow_rule_batch.canonical_draft.refresh:"
                        "default:bank_flow_rule_batch_draft:2026-05"
                    ),
                    "payload": {
                        "scope_type": "bank_flow_rule_batch_draft",
                        "scope_key": "2026-05",
                        "reason": "unit_test",
                        "metadata": {
                            "trigger": "bank_fact_change",
                            "source": "test",
                        },
                    },
                },
                {
                    "event_type": "bank_flow_rule_batch.canonical_draft.refresh",
                    "aggregate_type": "bank_flow_rule_batch",
                    "aggregate_id": "all",
                    "scope_type": "bank_flow_rule_batch_draft",
                    "scope_key": "all",
                    "dedupe_key": (
                        "bank_flow_rule_batch.canonical_draft.refresh:"
                        "default:bank_flow_rule_batch_draft:all"
                    ),
                    "payload": {
                        "scope_type": "bank_flow_rule_batch_draft",
                        "scope_key": "all",
                        "reason": "unit_test",
                        "metadata": {
                            "trigger": "bank_fact_change",
                            "source": "test",
                        },
                    },
                },
            ],
        )

    def test_enqueue_returns_false_without_queue_repository(self) -> None:
        producer = BankFlowRuleBatchCanonicalDraftProducer(
            queue_repository_provider=lambda: None
        )

        enqueued = producer.enqueue(["all"], reason="unit_test")

        self.assertFalse(enqueued)

    def test_dedupe_identity_is_stable_across_trigger_reasons(self) -> None:
        queue = RecordingQueueRepository()
        producer = BankFlowRuleBatchCanonicalDraftProducer(
            queue_repository_provider=lambda: queue
        )

        producer.enqueue(["2026-05"], reason="bank_import")
        producer.enqueue(["2026-05"], reason="settings_reset_completed")

        self.assertEqual(
            queue.calls[0]["dedupe_key"],
            queue.calls[1]["dedupe_key"],
        )
        self.assertEqual(
            queue.calls[0]["dedupe_key"],
            (
                "bank_flow_rule_batch.canonical_draft.refresh:"
                "default:bank_flow_rule_batch_draft:2026-05"
            ),
        )
        self.assertNotEqual(
            queue.calls[0]["payload"]["metadata"]["trigger"],
            queue.calls[1]["payload"]["metadata"]["trigger"],
        )

    def test_trigger_mapping_covers_all_canonical_draft_sources(self) -> None:
        self.assertEqual(
            BankFlowRuleBatchCanonicalDraftProducer.trigger_for_reason("bank_import"),
            "bank_fact_change",
        )
        self.assertEqual(
            BankFlowRuleBatchCanonicalDraftProducer.trigger_for_reason("category_rule_changed"),
            "effective_tag_rule_change",
        )
        self.assertEqual(
            BankFlowRuleBatchCanonicalDraftProducer.trigger_for_reason("settings_reset_completed"),
            "settings_reset",
        )
        self.assertEqual(
            BankFlowRuleBatchCanonicalDraftProducer.trigger_for_reason("operator_replay"),
            "repair_replay",
        )


if __name__ == "__main__":
    unittest.main()
