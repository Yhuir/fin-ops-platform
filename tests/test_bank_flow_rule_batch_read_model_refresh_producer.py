from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_flow_rule_batch_read_model_refresh_producer import (
    BankFlowRuleBatchReadModelRefreshProducer,
)


class RecordingRefreshGateway:
    def __init__(self, *, can_enqueue: bool = True) -> None:
        self._can_enqueue = can_enqueue
        self.calls: list[dict[str, object]] = []

    def can_enqueue(self) -> bool:
        return self._can_enqueue

    def enqueue_many(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        self.calls.append(
            {
                "scope_type": scope_type,
                "scope_keys": list(scope_keys),
                "reason": reason,
                "metadata": metadata,
            }
        )
        return [f"job:{scope_key}" for scope_key in scope_keys]


class BankFlowRuleBatchReadModelRefreshProducerTests(unittest.TestCase):
    def test_enqueue_normalizes_scope_keys_and_uses_bank_flow_scope(self) -> None:
        gateway = RecordingRefreshGateway()
        producer = BankFlowRuleBatchReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        jobs = producer.enqueue_scope_keys(
            [" 2026-05 ", "", "bad", "all", "2026-05"],
            reason="unit_test",
            metadata={"source": "test"},
        )

        self.assertEqual(jobs, ["job:2026-05", "job:all"])
        self.assertEqual(
            gateway.calls,
            [
                {
                    "scope_type": "bank_flow_rule_batch",
                    "scope_keys": ["2026-05", "all"],
                    "reason": "unit_test",
                    "metadata": {"source": "test"},
                }
            ],
        )

    def test_enqueue_returns_false_without_queue_gateway(self) -> None:
        gateway = RecordingRefreshGateway(can_enqueue=False)
        producer = BankFlowRuleBatchReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        enqueued = producer.enqueue(["all"], reason="unit_test")

        self.assertFalse(enqueued)
        self.assertEqual(gateway.calls, [])


if __name__ == "__main__":
    unittest.main()
