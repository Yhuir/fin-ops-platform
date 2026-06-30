from __future__ import annotations

import unittest

from fin_ops_platform.services.operation_freshness_barrier import (
    OperationFreshnessBarrierService,
    OperationFreshnessTarget,
    targets_from_payload,
)


class OperationFreshnessBarrierServiceTests(unittest.TestCase):
    def test_reports_fresh_when_target_scope_readiness_is_fresh(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "workbench_relation": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-02",
                                "status": "fresh",
                                "updated_at": "2026-06-14T10:00:00+00:00",
                            }
                        ],
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {"workbench-relation": {"status": "ready", "heartbeat_lag_seconds": 1}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("workbench_relation", "2026-02")])

        self.assertEqual(payload["status"], "fresh")
        self.assertTrue(payload["fresh"])
        self.assertEqual(payload["targets"][0]["status"], "fresh")
        self.assertEqual(payload["targets"][0]["worker_status"], "ready")

    def test_dirty_scope_keeps_target_refreshing_even_when_readiness_was_fresh(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "no_oa_bank_batch": {
                        "status": "refreshing",
                        "scopes": [
                            {
                                "scope_type": "no_oa_bank_batch",
                                "scope_key": "2026-05",
                                "status": "refreshing",
                                "updated_at": "2026-06-14T10:00:01+00:00",
                            },
                            {
                                "scope_type": "no_oa_bank_batch",
                                "scope_key": "all",
                                "status": "fresh",
                            },
                        ],
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("no_oa_bank_batch", "2026-05")])

        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["refreshing_targets"][0]["scope_key"], "2026-05")

    def test_bank_flow_rule_batch_target_uses_independent_readiness(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "bank_flow_rule_batch": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "bank_flow_rule_batch",
                                "scope_key": "2026-05",
                                "status": "fresh",
                            }
                        ],
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {"bank-flow-rule-batch": {"status": "ready"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_flow_rule_batch", "2026-05")])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["targets"][0]["read_model_key"], "bank_flow_rule_batch")
        self.assertEqual(payload["targets"][0]["scope_type"], "bank_flow_rule_batch")
        self.assertEqual(payload["targets"][0]["worker_status"], "ready")

    def test_bank_flow_rule_batch_target_does_not_fall_back_to_no_oa_readiness(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "no_oa_bank_batch": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "no_oa_bank_batch",
                                "scope_key": "2026-05",
                                "status": "fresh",
                            }
                        ],
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {"no-oa-bank-batch": {"status": "ready"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_flow_rule_batch", "2026-05")])

        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["targets"][0]["scope_type"], "bank_flow_rule_batch")
        self.assertEqual(payload["targets"][0]["raw_status"], "missing")

    def test_target_scope_outbox_pending_keeps_target_refreshing_when_readiness_was_fresh(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "workbench_relation": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-03",
                                "status": "fresh",
                                "updated_at": "2026-06-17T10:49:43+00:00",
                            }
                        ],
                    }
                },
                "outbox_statuses": {
                    "workbench_relation.read_model.refresh": {
                        "status": "pending",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-03",
                                "status": "pending",
                                "updated_at": "2026-06-17T10:49:44+00:00",
                            }
                        ],
                    }
                },
                "worker_statuses": {"workbench-relation": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("workbench_relation", "2026-03")])

        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["refreshing_targets"][0]["reason"], "refresh outbox pending")

    def test_bank_account_balance_all_dirty_scope_keeps_accounts_target_refreshing(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "bank_account_balance": {
                        "status": "refreshing",
                        "scopes": [
                            {
                                "scope_type": "bank_account_balance",
                                "scope_key": "all",
                                "status": "refreshing",
                                "updated_at": "2026-06-24T10:00:01+00:00",
                            }
                        ],
                    },
                    "bank_detail": {
                        "status": "fresh",
                        "scopes": [{"scope_type": "bank_detail", "scope_key": "2026-03", "status": "fresh"}],
                    },
                },
                "outbox_statuses": {},
                "worker_statuses": {"bank-account-balance": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_account_balance")])

        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["refreshing_targets"][0]["scope_type"], "bank_account_balance")
        self.assertEqual(payload["refreshing_targets"][0]["scope_key"], "all")
        self.assertEqual(payload["refreshing_targets"][0]["worker_status"], "running")

    def test_bank_account_balance_all_outbox_pending_keeps_accounts_target_refreshing(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "bank_account_balance": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "bank_account_balance",
                                "scope_key": "all",
                                "status": "fresh",
                                "updated_at": "2026-06-24T10:00:01+00:00",
                            }
                        ],
                    }
                },
                "outbox_statuses": {
                    "bank_account_balance.read_model.refresh": {
                        "status": "pending",
                        "scopes": [
                            {"scope_type": "bank_account_balance", "scope_key": "all", "status": "pending"}
                        ],
                    },
                    "bank_detail.read_model.refresh": {
                        "status": "pending",
                        "scopes": [{"scope_type": "bank_detail", "scope_key": "2026-03", "status": "pending"}],
                    },
                },
                "worker_statuses": {"bank-account-balance": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_account_balance")])

        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["refreshing_targets"][0]["reason"], "refresh outbox pending")
        self.assertEqual(payload["refreshing_targets"][0]["scope_type"], "bank_account_balance")
        self.assertEqual(payload["refreshing_targets"][0]["scope_key"], "all")

    def test_other_read_model_outbox_pending_does_not_block_bank_account_balance_all_target(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "bank_account_balance": {
                        "status": "fresh",
                        "scopes": [
                            {"scope_type": "bank_account_balance", "scope_key": "all", "status": "fresh"}
                        ],
                    }
                },
                "outbox_statuses": {
                    "bank_detail.read_model.refresh": {
                        "status": "pending",
                        "scopes": [{"scope_type": "bank_detail", "scope_key": "2026-03", "status": "pending"}],
                    }
                },
                "worker_statuses": {"bank-account-balance": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_account_balance")])

        self.assertEqual(payload["status"], "fresh")
        self.assertTrue(payload["fresh"])
        self.assertEqual(payload["targets"][0]["scope_type"], "bank_account_balance")
        self.assertEqual(payload["targets"][0]["scope_key"], "all")
        self.assertNotIn("reason", payload["targets"][0])

    def test_other_scope_outbox_pending_does_not_block_fresh_target_scope(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "workbench_relation": {
                        "status": "fresh",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-03",
                                "status": "fresh",
                                "updated_at": "2026-06-17T10:49:52+00:00",
                            }
                        ],
                    }
                },
                "outbox_statuses": {
                    "workbench_relation.read_model.refresh": {
                        "status": "pending",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-04",
                                "status": "pending",
                                "updated_at": "2026-06-17T10:49:54+00:00",
                            }
                        ],
                    }
                },
                "worker_statuses": {"workbench-relation": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("workbench_relation", "2026-03")])

        self.assertEqual(payload["status"], "fresh")
        self.assertTrue(payload["fresh"])
        self.assertEqual(payload["targets"][0]["status"], "fresh")
        self.assertNotIn("reason", payload["targets"][0])

    def test_bank_detail_target_uses_exact_month_scope_for_operation_barrier(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "bank_detail": {
                        "status": "fresh",
                        "scopes": [
                            {"scope_type": "bank_detail", "scope_key": "2026-03", "status": "fresh"},
                            {"scope_type": "bank_detail", "scope_key": "2026-04", "status": "fresh"},
                        ],
                    }
                },
                "outbox_statuses": {
                    "bank_detail.read_model.refresh": {
                        "status": "pending",
                        "scopes": [
                            {"scope_type": "bank_detail", "scope_key": "2026-04", "status": "pending"}
                        ],
                    }
                },
                "worker_statuses": {"bank-detail": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("bank_detail", "2026-03")])

        self.assertEqual(payload["status"], "fresh")
        self.assertTrue(payload["fresh"])
        self.assertEqual(payload["targets"][0]["scope_key"], "2026-03")
        self.assertEqual(payload["targets"][0]["worker_status"], "running")

    def test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "invoice_lifecycle": {
                        "status": "fresh",
                        "scopes": [
                            {"scope_type": "invoice_lifecycle", "scope_key": "2026-03", "status": "fresh"},
                            {"scope_type": "invoice_lifecycle", "scope_key": "2026-04", "status": "fresh"},
                        ],
                    }
                },
                "outbox_statuses": {
                    "invoice_lifecycle.read_model.refresh": {
                        "status": "pending",
                        "scopes": [
                            {"scope_type": "invoice_lifecycle", "scope_key": "2026-04", "status": "pending"}
                        ],
                    }
                },
                "worker_statuses": {"invoice-lifecycle": {"status": "running"}},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("invoice_lifecycle", "2026-03")])

        self.assertEqual(payload["status"], "fresh")
        self.assertTrue(payload["fresh"])
        self.assertEqual(payload["targets"][0]["scope_type"], "invoice_lifecycle")
        self.assertEqual(payload["targets"][0]["scope_key"], "2026-03")
        self.assertEqual(payload["targets"][0]["worker_status"], "running")

    def test_outbox_failure_blocks_target_even_if_readiness_is_fresh(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {
                    "turnover_ledger": {
                        "status": "fresh",
                        "scope_type": "turnover_ledger",
                        "scope_key": "all",
                    }
                },
                "outbox_statuses": {
                    "turnover_ledger.read_model.refresh": {
                        "status": "failed",
                        "last_error": "worker crashed",
                        "updated_at": "2026-06-14T10:00:02+00:00",
                    }
                },
                "worker_statuses": {},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("turnover_ledger", "all")])

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocked_targets"][0]["reason"], "refresh outbox blocked")
        self.assertEqual(payload["blocked_targets"][0]["last_error"], "worker crashed")

    def test_unknown_read_model_is_blocked_not_fake_fresh(self) -> None:
        service = OperationFreshnessBarrierService(
            runtime_snapshot_provider=lambda: {
                "read_model_statuses": {},
                "outbox_statuses": {},
                "worker_statuses": {},
            }
        )

        payload = service.status_payload([OperationFreshnessTarget("legacy_shadow_model", "all")])

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["targets"][0]["reason"], "unknown_read_model")

    def test_targets_from_payload_accepts_single_target_contract(self) -> None:
        targets = targets_from_payload({"read_model_key": "bank_detail", "scope_key": "all"})

        self.assertEqual(targets, [OperationFreshnessTarget("bank_detail", "all", "bank_detail")])

    def test_targets_from_payload_rejects_non_object_entries(self) -> None:
        with self.assertRaises(ValueError):
            targets_from_payload({"targets": ["workbench_relation"]})


if __name__ == "__main__":
    unittest.main()
