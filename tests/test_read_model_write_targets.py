from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_write_targets import (
    freshness_targets,
    normalized_scope_keys,
    write_target_envelope,
)


class ReadModelWriteTargetsTests(unittest.TestCase):
    def test_normalized_scope_keys_dedupes_and_keeps_order(self) -> None:
        self.assertEqual(normalized_scope_keys(["2026-05", "", "2026-05", "all"]), ["2026-05", "all"])

    def test_freshness_targets_use_operation_barrier_shape(self) -> None:
        self.assertEqual(
            freshness_targets("workbench_relation", ["2026-05"], scope_type="workbench_relation"),
            [
                {
                    "read_model_key": "workbench_relation",
                    "scope_key": "2026-05",
                    "scope_type": "workbench_relation",
                }
            ],
        )

    def test_write_target_envelope_preserves_legacy_scope_fields_and_barrier_targets(self) -> None:
        payload = write_target_envelope(read_model_key="no_oa_bank_batch", scope_keys=["2026-05", "2026-05"])

        self.assertEqual(payload["affected_scope_keys"], ["2026-05"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["freshness_targets"], [{"read_model_key": "no_oa_bank_batch", "scope_key": "2026-05"}])
        self.assertEqual(payload["operation_barrier_targets"], payload["freshness_targets"])

    def test_write_target_envelope_accepts_prebuilt_targets(self) -> None:
        payload = write_target_envelope(
            scope_keys=["2026-05"],
            targets=[
                {"readModelKey": "turnover_ledger", "scopeKey": "all"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
            ],
        )

        self.assertEqual(payload["affected_scope_keys"], ["2026-05"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [
                {"read_model_key": "turnover_ledger", "scope_key": "all"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
            ],
        )

    def test_write_target_envelope_falls_back_to_scope_when_no_scope_is_available(self) -> None:
        payload = write_target_envelope(read_model_key="bank_account_balance", scope_keys=[], fallback_scope_key="all")

        self.assertEqual(payload["read_model_scope_keys"], ["all"])
        self.assertEqual(payload["freshness_targets"], [{"read_model_key": "bank_account_balance", "scope_key": "all"}])


if __name__ == "__main__":
    unittest.main()
