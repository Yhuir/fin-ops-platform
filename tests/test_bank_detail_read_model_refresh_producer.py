from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_read_model_refresh_producer import BankDetailReadModelRefreshProducer


class _RefreshGateway:
    def __init__(self, *, can_enqueue: bool = True) -> None:
        self._can_enqueue = can_enqueue
        self.enqueued: list[tuple[str, list[str], str, dict[str, object] | None]] = []

    def can_enqueue(self) -> bool:
        return self._can_enqueue

    def enqueue_many(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        self.enqueued.append((scope_type, list(scope_keys), reason, metadata))
        return True


class _RedisHelper:
    def __init__(self) -> None:
        self.wakeups: list[tuple[str, dict[str, object]]] = []

    def publish_wakeup(self, channel: str, payload: dict[str, object]) -> None:
        self.wakeups.append((channel, dict(payload)))


class BankDetailReadModelRefreshProducerTests(unittest.TestCase):
    def test_enqueue_uses_gateway_and_publishes_optional_wakeup_per_scope(self) -> None:
        gateway = _RefreshGateway()
        redis_helper = _RedisHelper()
        producer = BankDetailReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
            redis_helper_provider=lambda: redis_helper,
        )

        enqueued = producer.enqueue(
            [" 2026-01 ", "", "2026-02"],
            reason="rules_changed",
            metadata={"actor": "tester"},
        )

        self.assertTrue(enqueued)
        self.assertEqual(gateway.enqueued, [("bank_detail", ["2026-01", "2026-02"], "rules_changed", {"actor": "tester"})])
        self.assertEqual(
            redis_helper.wakeups,
            [
                ("bank_detail_read_model_refresh", {"scope_key": "2026-01"}),
                ("bank_detail_read_model_refresh", {"scope_key": "2026-02"}),
            ],
        )

    def test_enqueue_returns_false_without_wakeup_when_gateway_unavailable(self) -> None:
        gateway = _RefreshGateway(can_enqueue=False)
        redis_helper = _RedisHelper()
        producer = BankDetailReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
            redis_helper_provider=lambda: redis_helper,
        )

        self.assertFalse(producer.enqueue(["2026-01"], reason="runtime_unavailable"))
        self.assertEqual(gateway.enqueued, [])
        self.assertEqual(redis_helper.wakeups, [])


if __name__ == "__main__":
    unittest.main()
