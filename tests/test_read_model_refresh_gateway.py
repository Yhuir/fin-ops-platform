import unittest
from types import SimpleNamespace


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class ReadModelRefreshGatewayTests(unittest.TestCase):
    def test_cost_statistics_policy_normalizes_validates_and_dedupes_legacy_scopes(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "cost_statistics",
            ["2026-03", "2026-03", "all", "active:2026-03", "all:2026-04"],
            reason="unit_test",
        )

        self.assertEqual(
            enqueued,
            [
                "active:2026-03",
                "all:2026-03",
                "active:2026-04",
                "all:2026-04",
                "active:all",
                "all:all",
            ],
        )
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-03", "unit_test"),
                ("cost_statistics", "all:2026-03", "unit_test"),
                ("cost_statistics", "active:2026-04", "unit_test"),
                ("cost_statistics", "all:2026-04", "unit_test"),
                ("cost_statistics", "active:all", "unit_test"),
                ("cost_statistics", "all:all", "unit_test"),
            ],
        )

    def test_unknown_or_generic_scope_types_are_preserved_and_deduped(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many("tax_offset", ["2026-03", "2026-03", "all"], reason="unit_test")

        self.assertEqual(enqueued, ["2026-03", "all"])
        self.assertEqual(
            queue.refreshes,
            [
                ("tax_offset", "2026-03", "unit_test"),
                ("tax_offset", "all", "unit_test"),
            ],
        )

    def test_rejects_cost_statistics_scope_that_cannot_be_normalized(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        gateway = ReadModelRefreshGateway(queue_repository=SimpleNamespace(enqueue_read_model_refresh=lambda **_kwargs: None))

        with self.assertRaises(ReadModelScopeError):
            gateway.enqueue_many("cost_statistics", ["archived:2026-03"], reason="unit_test")


if __name__ == "__main__":
    unittest.main()
