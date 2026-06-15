import unittest
from types import SimpleNamespace


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[dict[str, object]] = []
        self.active_refreshes: set[tuple[str, str, str]] = set()
        self.active_checks: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.refreshes.append(dict(kwargs))

    def read_model_refresh_is_active(self, *, tenant_id: str, scope_type: str, scope_key: str) -> bool:
        key = (tenant_id, scope_type, scope_key)
        self.active_checks.append(key)
        return key in self.active_refreshes


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
                {"scope_type": "cost_statistics", "scope_key": "active:2026-03", "reason": "unit_test"},
                {"scope_type": "cost_statistics", "scope_key": "all:2026-03", "reason": "unit_test"},
                {"scope_type": "cost_statistics", "scope_key": "active:2026-04", "reason": "unit_test"},
                {"scope_type": "cost_statistics", "scope_key": "all:2026-04", "reason": "unit_test"},
                {"scope_type": "cost_statistics", "scope_key": "active:all", "reason": "unit_test"},
                {"scope_type": "cost_statistics", "scope_key": "all:all", "reason": "unit_test"},
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
                {"scope_type": "tax_offset", "scope_key": "2026-03", "reason": "unit_test"},
                {"scope_type": "tax_offset", "scope_key": "all", "reason": "unit_test"},
            ],
        )

    def test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "no_oa_bank_batch",
            ["2026-06", "all", "2026-06"],
            reason="unit_test",
        )

        self.assertEqual(enqueued, ["2026-06", "all"])
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "no_oa_bank_batch", "scope_key": "2026-06", "reason": "unit_test"},
                {"scope_type": "no_oa_bank_batch", "scope_key": "all", "reason": "unit_test"},
            ],
        )
        with self.assertRaises(ReadModelScopeError):
            gateway.enqueue_many("no_oa_bank_batch", ["active:2026-06"], reason="unit_test")

    def test_metadata_is_passed_to_queue_repository(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench_relation",
            ["2026-03"],
            reason="pair_relation_changed",
            metadata={"action_name": "withdraw_link"},
        )

        self.assertEqual(enqueued, ["2026-03"])
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-03",
                    "reason": "pair_relation_changed",
                    "metadata": {"action_name": "withdraw_link"},
                }
            ],
        )

    def test_ensure_refresh_reason_does_not_bump_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "bank_detail", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "bank_detail",
            ["2026-02"],
            reason="pending_invoice_sql_projection",
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [("default", "bank_detail", "2026-02")])
        self.assertEqual(queue.refreshes, [])

    def test_bank_detail_all_shard_reason_does_not_bump_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "bank_detail", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "bank_detail",
            ["2026-02"],
            reason="bank_detail_all_shard",
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [("default", "bank_detail", "2026-02")])
        self.assertEqual(queue.refreshes, [])

    def test_mutating_refresh_reason_still_bumps_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "bank_detail", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "bank_detail",
            ["2026-02"],
            reason="workbench_relation_changed",
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "bank_detail", "scope_key": "2026-02", "reason": "workbench_relation_changed"}],
        )

    def test_rejects_cost_statistics_scope_that_cannot_be_normalized(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        gateway = ReadModelRefreshGateway(queue_repository=SimpleNamespace(enqueue_read_model_refresh=lambda **_kwargs: None))

        with self.assertRaises(ReadModelScopeError):
            gateway.enqueue_many("cost_statistics", ["archived:2026-03"], reason="unit_test")


if __name__ == "__main__":
    unittest.main()
