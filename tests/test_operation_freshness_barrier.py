from __future__ import annotations

import unittest

from fin_ops_platform.services.operation_freshness_barrier import (
    OperationFreshnessBarrierService,
    OperationFreshnessTarget,
    targets_from_payload,
)


def _service(
    *,
    read_model_statuses: dict[str, object],
    outbox_statuses: dict[str, object] | None = None,
    worker_statuses: dict[str, object] | None = None,
) -> OperationFreshnessBarrierService:
    return OperationFreshnessBarrierService(
        runtime_snapshot_provider=lambda: {
            "read_model_statuses": read_model_statuses,
            "outbox_statuses": outbox_statuses or {},
            "worker_statuses": worker_statuses or {},
        }
    )


class OperationFreshnessBarrierServiceTests(unittest.TestCase):
    def test_reports_fresh_for_active_shared_scope(self) -> None:
        service = _service(
            read_model_statuses={
                "workbench_relation": {
                    "status": "fresh",
                    "scopes": [
                        {
                            "scope_type": "workbench_relation",
                            "scope_key": "2026-02",
                            "status": "fresh",
                        }
                    ],
                }
            },
            worker_statuses={"workbench-relation": {"status": "ready"}},
        )

        payload = service.status_payload(
            [OperationFreshnessTarget("workbench_relation", "2026-02")]
        )

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["targets"][0]["worker_status"], "ready")

    def test_pending_exact_scope_keeps_active_shared_target_refreshing(self) -> None:
        service = _service(
            read_model_statuses={
                "search": {
                    "status": "fresh",
                    "scopes": [
                        {
                            "scope_type": "search",
                            "scope_key": "2026-03",
                            "status": "fresh",
                        }
                    ],
                }
            },
            outbox_statuses={
                "search.read_model.refresh": {
                    "status": "pending",
                    "scopes": [
                        {
                            "scope_type": "search",
                            "scope_key": "2026-03",
                            "status": "pending",
                        }
                    ],
                }
            },
        )

        payload = service.status_payload(
            [OperationFreshnessTarget("search", "2026-03")]
        )

        self.assertEqual(payload["status"], "refreshing")
        self.assertEqual(
            payload["refreshing_targets"][0]["reason"],
            "refresh outbox pending",
        )

    def test_other_scope_pending_does_not_block_fresh_target(self) -> None:
        service = _service(
            read_model_statuses={
                "workbench_relation": {
                    "status": "fresh",
                    "scopes": [
                        {
                            "scope_type": "workbench_relation",
                            "scope_key": "2026-03",
                            "status": "fresh",
                        }
                    ],
                }
            },
            outbox_statuses={
                "workbench_relation.read_model.refresh": {
                    "status": "pending",
                    "scopes": [
                        {
                            "scope_type": "workbench_relation",
                            "scope_key": "2026-04",
                            "status": "pending",
                        }
                    ],
                }
            },
        )

        payload = service.status_payload(
            [OperationFreshnessTarget("workbench_relation", "2026-03")]
        )

        self.assertEqual(payload["status"], "fresh")

    def test_failed_active_shared_outbox_blocks_target(self) -> None:
        service = _service(
            read_model_statuses={
                "no_oa_bank_batch": {
                    "status": "fresh",
                    "scope_type": "no_oa_bank_batch",
                    "scope_key": "all",
                }
            },
            outbox_statuses={
                "no_oa_bank_batch.read_model.refresh": {
                    "status": "failed",
                    "last_error": "worker crashed",
                }
            },
        )

        payload = service.status_payload(
            [OperationFreshnessTarget("no_oa_bank_batch", "all")]
        )

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["blocked_targets"][0]["last_error"], "worker crashed")

    def test_retired_page_read_model_is_unknown_and_blocked(self) -> None:
        service = _service(read_model_statuses={})

        for retired_key in (
            "workbench",
            "bank_detail",
            "bank_account_balance",
            "pending_invoice",
            "invoice_lifecycle",
            "input_invoice_usage",
            "output_invoice_collection",
            "oa_pending_payment",
            "tax_offset",
            "bank_flow_rule_batch",
        ):
            with self.subTest(retired_key=retired_key):
                payload = service.status_payload(
                    [OperationFreshnessTarget(retired_key, "all")]
                )
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(
                    payload["targets"][0]["reason"],
                    "unknown_read_model",
                )

    def test_targets_from_payload_uses_active_registry_scope_type(self) -> None:
        targets = targets_from_payload(
            {"read_model_key": "search", "scope_key": "2026-05"}
        )

        self.assertEqual(
            targets,
            [OperationFreshnessTarget("search", "2026-05", "search")],
        )

    def test_targets_from_payload_rejects_non_object_entries(self) -> None:
        with self.assertRaises(ValueError):
            targets_from_payload({"targets": ["workbench_relation"]})


if __name__ == "__main__":
    unittest.main()
