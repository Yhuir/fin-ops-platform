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

        enqueued = gateway.enqueue_many("example", ["2026-03", "2026-03", "all"], reason="unit_test")

        self.assertEqual(enqueued, ["2026-03", "all"])
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "example", "scope_key": "2026-03", "reason": "unit_test"},
                {"scope_type": "example", "scope_key": "all", "reason": "unit_test"},
            ],
        )

    def test_registered_month_or_all_read_models_reject_invalid_scope_keys(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        registered_scope_types = [
            "bank_detail",
            "input_invoice_usage",
            "invoice_lifecycle",
            "oa_pending_payment",
            "output_invoice_collection",
            "search",
            "tax_offset",
            "turnover_ledger",
            "workbench",
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

    def test_bank_account_balance_policy_accepts_only_all_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "bank_account_balance",
            ["all", "all"],
            reason="unit_test",
        )

        self.assertEqual(enqueued, ["all"])
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "bank_account_balance", "scope_key": "all", "reason": "unit_test"}],
        )
        for invalid_scope_key in ["2026-03", "account:legacy", "active:2026-03"]:
            with self.subTest(invalid_scope_key=invalid_scope_key):
                with self.assertRaises(ReadModelScopeError):
                    gateway.enqueue_many("bank_account_balance", [invalid_scope_key], reason="unit_test")
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "bank_account_balance", "scope_key": "all", "reason": "unit_test"}],
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

    def test_pending_invoice_policy_accepts_aggregate_base_and_month_scopes(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "pending_invoice",
            [
                "expense:all",
                "income:cash_income",
                "expense:bank_statement_as_invoice:2026-02",
                "expense:no_invoice_required:2026-02",
                "income:all:2026-02",
                "income:requires_invoice:2026-02",
                "income:all:2026-02",
            ],
            reason="unit_test",
        )

        self.assertEqual(
            enqueued,
            [
                "expense:all",
                "income:cash_income",
                "expense:bank_statement_as_invoice:2026-02",
                "expense:no_invoice_required:2026-02",
                "income:all:2026-02",
                "income:requires_invoice:2026-02",
            ],
        )
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "pending_invoice", "scope_key": "expense:all", "reason": "unit_test"},
                {"scope_type": "pending_invoice", "scope_key": "income:cash_income", "reason": "unit_test"},
                {
                    "scope_type": "pending_invoice",
                    "scope_key": "expense:bank_statement_as_invoice:2026-02",
                    "reason": "unit_test",
                },
                {
                    "scope_type": "pending_invoice",
                    "scope_key": "expense:no_invoice_required:2026-02",
                    "reason": "unit_test",
                },
                {"scope_type": "pending_invoice", "scope_key": "income:all:2026-02", "reason": "unit_test"},
                {"scope_type": "pending_invoice", "scope_key": "income:requires_invoice:2026-02", "reason": "unit_test"},
            ],
        )

    def test_pending_invoice_policy_rejects_bare_month_and_invalid_direction(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        for invalid_scope_key in ["2026-02", "global", "refund:all", "income", "income:all:202602"]:
            with self.subTest(invalid_scope_key=invalid_scope_key):
                with self.assertRaises(ReadModelScopeError):
                    gateway.enqueue_many("pending_invoice", [invalid_scope_key], reason="unit_test")
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_policy_rejects_global_all_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        with self.assertRaises(ReadModelScopeError):
            gateway.enqueue_many("pending_invoice", ["all"], reason="unit_test")
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_policy_rejects_unsupported_filter_groups(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
        from fin_ops_platform.services.read_model_scope_policy import ReadModelScopeError

        queue = QueueRecorder()
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        for invalid_scope_key in [
            "expense:cash_income",
            "expense:unknown_filter:2026-02",
            "income:bank_statement_as_invoice",
            "income:unknown_filter:2026-02",
        ]:
            with self.subTest(invalid_scope_key=invalid_scope_key):
                with self.assertRaises(ReadModelScopeError):
                    gateway.enqueue_many("pending_invoice", [invalid_scope_key], reason="unit_test")
        self.assertEqual(queue.refreshes, [])

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

    def test_force_refresh_is_not_coalesced_with_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "bank_detail", "2026-02"))
        gateway = ReadModelRefreshGateway(queue_repository=queue)

        enqueued = gateway.enqueue_many(
            "bank_detail",
            ["2026-02"],
            reason="bank_detail_all_shard",
            metadata={"force_refresh": True},
        )

        self.assertEqual(enqueued, ["2026-02"])
        self.assertEqual(queue.active_checks, [])
        self.assertEqual(
            queue.refreshes,
            [
                {
                    "scope_type": "bank_detail",
                    "scope_key": "2026-02",
                    "reason": "bank_detail_all_shard",
                    "metadata": {"force_refresh": True},
                }
            ],
        )

    def test_cost_statistics_shard_convergence_reasons_do_not_bump_active_scope(self) -> None:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        for reason in ("cost_statistics_all_shard", "cost_statistics_shard_converged"):
            with self.subTest(reason=reason):
                queue = QueueRecorder()
                queue.active_refreshes.add(("default", "cost_statistics", "active:all"))
                gateway = ReadModelRefreshGateway(queue_repository=queue)

                enqueued = gateway.enqueue_many(
                    "cost_statistics",
                    ["active:all"],
                    reason=reason,
                )

                self.assertEqual(enqueued, ["active:all"])
                self.assertEqual(queue.active_checks, [("default", "cost_statistics", "active:all")])
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
