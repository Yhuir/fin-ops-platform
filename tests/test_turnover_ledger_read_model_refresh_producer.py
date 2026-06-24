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


class _Repository:
    def __init__(self, *, fail_clear: bool = False) -> None:
        self.fail_clear = fail_clear
        self.clear_calls = 0

    def clear_turnover_ledger_rows(self) -> None:
        self.clear_calls += 1
        if self.fail_clear:
            raise RuntimeError("clear unavailable")


class TurnoverLedgerReadModelRefreshProducerTests(unittest.TestCase):
    def test_enqueue_normalizes_to_month_or_all_and_uses_gateway_boundary(self) -> None:
        gateway = _RefreshGateway()
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
            read_repository_provider=lambda: _Repository(),
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
            read_repository_provider=lambda: _Repository(),
        )

        self.assertTrue(producer.enqueue(["", "invalid"], reason="fallback"))

        self.assertEqual(gateway.enqueued, [("turnover_ledger", ["all"], "fallback", None)])

    def test_enqueue_returns_false_when_gateway_unavailable(self) -> None:
        gateway = _RefreshGateway(can_enqueue=False)
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: gateway,
            read_repository_provider=lambda: _Repository(),
        )

        self.assertFalse(producer.enqueue(["2026-02"], reason="runtime_unavailable"))
        self.assertEqual(gateway.enqueued, [])

    def test_clear_uses_turnover_repository_port_best_effort(self) -> None:
        repository = _Repository()
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: _RefreshGateway(),
            read_repository_provider=lambda: repository,
        )

        producer.clear_best_effort()

        self.assertEqual(repository.clear_calls, 1)

    def test_clear_swallows_repository_failure(self) -> None:
        repository = _Repository(fail_clear=True)
        producer = TurnoverLedgerReadModelRefreshProducer(
            refresh_gateway_provider=lambda: _RefreshGateway(),
            read_repository_provider=lambda: repository,
        )

        producer.clear_best_effort()

        self.assertEqual(repository.clear_calls, 1)


if __name__ == "__main__":
    unittest.main()
