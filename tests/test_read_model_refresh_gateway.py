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


class EventAwareQueueRecorder(QueueRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.active_events: set[tuple[str, str, str]] = set()
        self.active_event_checks: list[tuple[str, str, str]] = []

    def read_model_refresh_event_is_active(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
    ) -> bool:
        key = (tenant_id, scope_type, scope_key)
        self.active_event_checks.append(key)
        return key in self.active_events


class AtomicQueueRecorder(EventAwareQueueRecorder):
    def __init__(self, *, event: object | None) -> None:
        super().__init__()
        self.event = event
        self.atomic_refreshes: list[dict[str, object]] = []

    def enqueue_read_model_refresh_if_inactive(self, **kwargs: object) -> object | None:
        self.atomic_refreshes.append(dict(kwargs))
        return self.event


class BulkAtomicQueueRecorder(AtomicQueueRecorder):
    def __init__(self) -> None:
        super().__init__(event=None)
        self.atomic_refresh_batches: list[dict[str, object]] = []

    def enqueue_read_model_refreshes_if_inactive(self, **kwargs: object) -> list[object]:
        self.atomic_refresh_batches.append(dict(kwargs))
        return [
            SimpleNamespace(event_id=f"event-{index + 1}")
            for index, _scope_key in enumerate(kwargs["scope_keys"])
        ]


class ReadModelRefreshGatewayTests(unittest.TestCase):

    def test_unknown_or_generic_scope_types_are_preserved_and_deduped(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many("example", ["2026-03", "2026-03", "all"], reason="unit_test")

        self.assertEqual(enqueued, ["2026-03", "all"])
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "example", "scope_key": "2026-03", "reason": "unit_test"},
                {"scope_type": "example", "scope_key": "all", "reason": "unit_test"},
            ],
        )

    def test_active_shared_read_models_reject_invalid_scope_keys(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        registered_scope_types = [
            "workbench",
            "workbench_relation",
            "workbench_relation",
        ]

        for scope_type in registered_scope_types:
            with self.subTest(scope_type=scope_type):
                queue = QueueRecorder()
                gateway = ReadModelRefreshGateway(queue_repository=queue)

                enqueued = gateway.enqueue_many(scope_type, ["2026-03", "all", "2026-03"], reason="unit_test")

                self.assertEqual(enqueued, ["2026-03", "all"])
                with self.assertRaises(ReadModelScopeError):
                    gateway.enqueue_many(scope_type, ["active:2026-03"], reason="unit_test")

    def test_workbench_policy_accepts_all_and_month_scopes_only(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench",
            ["2026-06", "all", "2026-06"],
            reason="unit_test",
        )

        self.assertEqual(enqueued, ["2026-06", "all"])
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "workbench", "scope_key": "2026-06", "reason": "unit_test"},
                {"scope_type": "workbench", "scope_key": "all", "reason": "unit_test"},
            ],
        )
        with self.assertRaises(ReadModelScopeError):
            gateway.enqueue_many("workbench", ["active:2026-06"], reason="unit_test")

    def test_scope_policy_registry_contains_only_active_shared_read_models(self) -> None:
        from fin_ops_platform.services.read_model_scope_policy import (
            DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
        )

        self.assertEqual(
            set(DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.registered_scope_types()),
            {"workbench", "workbench_relation", "workbench", "workbench_relation"},
        )

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

    def test_active_shared_refresh_reasons_do_not_bump_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        for scope_type, scope_key, reason in (
            ("workbench", "2026-02", "api_no_oa_read_model_missing"),
            ("workbench_relation", "2026-02", "api_stale"),
            ("workbench_relation", "2026-02", "workbench_relation_month_shard"),
            ("workbench_relation", "2026-02", "workbench_relation_write_precondition"),
            ("workbench_relation", "2026-02", "workbench_relation_month_shard"),
        ):
            with self.subTest(reason=reason):
                queue = QueueRecorder()
                queue.active_refreshes.add(("default", scope_type, scope_key))
                gateway = ReadModelRefreshGateway(queue_repository=queue)

                enqueued = gateway.enqueue_many(
                    scope_type,
                    [scope_key],
                    reason=reason,
                )

                self.assertEqual(enqueued, [scope_key])
                self.assertEqual(queue.active_checks, [("default", scope_type, scope_key)])
                self.assertEqual(queue.refreshes, [])

    def test_retired_invoice_page_reasons_do_not_reuse_active_refresh_coalescing(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        for reason in (
            "bank_detail_all_shard",
            "bank_detail_relation_tags_read",
            "downstream_bank_tag_read",
            "input_invoice_usage_filter_options",
            "input_invoice_usage_month_shard",
            "input_invoice_usage_rows",
            "invoice_lifecycle_access_dependency",
            "invoice_lifecycle_month_shard",
            "invoice_usage_collection_sql_projection",
            "oa_pending_payment_month_shard",
            "output_invoice_collection_month_shard",
            "output_invoice_collection_rows",
            "pending_invoice_month_shard",
            "pending_invoice_sql_projection",
            "relation_dependency_gate",
            "tax_offset_all_shard",
            "workbench_all_shard",
        ):
            with self.subTest(reason=reason):
                queue = QueueRecorder()
                queue.active_refreshes.add(("default", "workbench_relation", "2026-02"))
                gateway = ReadModelRefreshGateway(queue_repository=queue)

                enqueued = gateway.enqueue_many(
                    "workbench_relation",
                    ["2026-02"],
                    reason=reason,
                )

                self.assertEqual(enqueued, ["2026-02"])
                self.assertEqual(queue.active_checks, [])
                self.assertEqual(
                    queue.refreshes,
                    [{"scope_type": "workbench_relation", "scope_key": "2026-02", "reason": reason}],
                )

    def test_workbench_relation_month_shard_reason_does_not_bump_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "workbench_relation", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench_relation",
            ["2026-02"],
            reason="workbench_relation_month_shard",
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [("default", "workbench_relation", "2026-02")])
        self.assertEqual(queue.refreshes, [])

    def test_force_refresh_is_not_coalesced_with_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "workbench_relation", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench_relation",
            ["2026-02"],
            reason="workbench_relation_month_shard",
            metadata={"force_refresh": True},
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-02",
                    "reason": "workbench_relation_month_shard",
                    "metadata": {"force_refresh": True},
                }
            ],
        )

    def test_orphan_dirty_scope_without_active_event_is_reenqueued(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = EventAwareQueueRecorder()
        queue.active_refreshes.add(("default", "workbench_relation", "all"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench_relation",
            ["all"],
            reason="workbench_relation_month_shard",
        )

        self.assertEqual(enqueued, ["all"])
        self.assertEqual(queue.active_event_checks, [("default", "workbench_relation", "all")])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "all",
                    "reason": "workbench_relation_month_shard",
                }
            ],
        )

    def test_active_refresh_event_is_still_coalesced(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = EventAwareQueueRecorder()
        queue.active_events.add(("default", "workbench_relation", "all"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        gateway.enqueue_many(
            "workbench_relation",
            ["all"],
            reason="workbench_relation_month_shard",
        )

        self.assertEqual(queue.active_event_checks, [("default", "workbench_relation", "all")])
        self.assertEqual(queue.refreshes, [])

    def test_api_refresh_uses_atomic_enqueue_without_check_then_enqueue_race(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = AtomicQueueRecorder(event=SimpleNamespace(event_id="event-1"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        events = gateway.enqueue_many_events(
            "workbench_relation",
            ["2026-02"],
            reason="api_page_stale",
        )

        self.assertEqual([event.event_id for event in events], ["event-1"])
        self.assertEqual(
            queue.atomic_refreshes,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-02",
                    "reason": "api_page_stale",
                }
            ],
        )
        self.assertEqual(queue.active_event_checks, [])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(queue.refreshes, [])

    def test_api_refresh_batches_exact_scopes_in_one_atomic_repository_call(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = BulkAtomicQueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        events = gateway.enqueue_many_events(
            "workbench_relation",
            ["2026-02", "2026-03"],
            reason="api_source_versions_stale",
        )

        self.assertEqual([event.event_id for event in events], ["event-1", "event-2"])
        self.assertEqual(
            queue.atomic_refresh_batches,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_keys": ["2026-02", "2026-03"],
                    "reason": "api_source_versions_stale",
                    "tenant_id": "default",
                    "priority": "normal",
                    "trace_id": None,
                    "metadata": None,
                }
            ],
        )
        self.assertEqual(queue.atomic_refreshes, [])
        self.assertEqual(queue.refreshes, [])

    def test_atomic_active_scope_returns_no_duplicate_event(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = AtomicQueueRecorder(event=None)
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        events = gateway.enqueue_many_events(
            "workbench_relation",
            ["all"],
            reason="workbench_relation_month_shard",
        )

        self.assertEqual(events, [])
        self.assertEqual(len(queue.atomic_refreshes), 1)
        self.assertEqual(queue.refreshes, [])

    def test_mutating_refresh_reason_still_bumps_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "workbench_relation", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "workbench_relation",
            ["2026-02"],
            reason="workbench_relation_changed",
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-02",
                    "reason": "workbench_relation_changed",
                }
            ],
        )

if __name__ == "__main__":
    unittest.main()
