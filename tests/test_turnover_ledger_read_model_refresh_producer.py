from __future__ import annotations

import unittest

from fin_ops_platform.services.turnover_ledger_read_model_refresh_producer import (
    TurnoverLedgerReadModelRefreshProducer,
)


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
    ) -> list[str]:
        self.enqueued.append((scope_type, list(scope_keys), reason, metadata))
        return list(scope_keys)


class TurnoverLedgerReadModelRefreshProducerTests(unittest.TestCase):
    def test_enqueue_normalizes_to_month_or_all_and_uses_gateway_boundary(self) -> None:
        gateway = _RefreshGateway()
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
        )

        enqueued = producer.enqueue(
            [" 2026-02 ", "invalid", "", "all", "2026-02", "2026-01"],
            reason="turnover_relation_changed",
            metadata={"source": "test"},
        )

        self.assertTrue(enqueued)
        self.assertEqual(
            gateway.enqueued,
            [
                (
                    "turnover_ledger",
                    ["2026-01", "2026-02", "all"],
                    "turnover_relation_changed",
                    {"source": "test"},
                )
            ],
        )

    def test_enqueue_defaults_empty_or_invalid_scope_to_all(self) -> None:
        gateway = _RefreshGateway()
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
        )

        self.assertTrue(producer.enqueue(["", "invalid"], reason="fallback"))

        self.assertEqual(gateway.enqueued, [("turnover_ledger", ["all"], "fallback", None)])

    def test_enqueue_returns_false_when_gateway_unavailable(self) -> None:
        gateway = _RefreshGateway(can_enqueue=False)
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
        )

        self.assertFalse(producer.enqueue(["2026-02"], reason="runtime_unavailable"))
        self.assertEqual(gateway.enqueued, [])

    def test_refresh_producer_does_not_expose_direct_clear_io(self) -> None:
        self.assertFalse(hasattr(TurnoverLedgerReadModelRefreshProducer, "clear_best_effort"))


if __name__ == "__main__":
    unittest.main()
