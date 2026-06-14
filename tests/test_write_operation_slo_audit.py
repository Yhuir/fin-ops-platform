from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from fin_ops_platform.tools import write_operation_slo_audit


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [dict(row) for row in self.rows]


def _event(
    *,
    scope_type: str,
    reason: str,
    action_name: str | None = None,
    seconds: float = 1.0,
    event_status: str = "done",
    dirty_status: str = "done",
    event_id: str | None = None,
) -> dict[str, object]:
    created_at = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)
    return {
        "event_id": event_id or f"{scope_type}-{reason}",
        "tenant_id": "default",
        "event_type": f"{scope_type}.read_model.refresh",
        "scope_type": scope_type,
        "scope_key": "all",
        "reason": reason,
        "action_name": action_name,
        "event_status": event_status,
        "source_version": 1,
        "created_at": created_at,
        "processed_at": created_at + timedelta(seconds=seconds),
        "updated_at": created_at + timedelta(seconds=seconds),
        "event_last_error": None,
        "raw_payload": {},
        "dirty_status": dirty_status,
        "dirty_last_error": None,
    }


class WriteOperationSloAuditTests(unittest.TestCase):
    def test_turnover_relation_profile_passes_only_with_all_required_refresh_scopes(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
                seconds=0.8,
            ),
            _event(
                scope_type="workbench",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
                seconds=1.1,
            ),
            _event(
                scope_type="workbench_relation",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
                seconds=1.2,
            ),
            _event(
                scope_type="cost_statistics",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
                seconds=0.9,
            ),
            _event(
                scope_type="search",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
                seconds=1.3,
            ),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_manual_closure_or_withdraw"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["failed_expectation_count"], 0)
        self.assertEqual(report["expectation_count"], 5)

    def test_missing_required_scope_fails_instead_of_claiming_write_chain_closed(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
            ),
            _event(
                scope_type="workbench",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
            ),
            _event(
                scope_type="workbench_relation",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
            ),
            _event(
                scope_type="cost_statistics",
                reason="turnover_relation_changed",
                action_name="withdraw_relation",
            ),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_manual_closure_or_withdraw"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_expectation_count"], 1)
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(missing[0]["scope_type"], "search")
        self.assertEqual(missing[0]["latest_error"], "no_recent_required_write_refresh_event")

    def test_slow_done_event_fails_target(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_extra_changed",
                action_name="relation_extra_update",
                seconds=6.0,
            ),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_relation_extra"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("p95_enqueue_to_done_ms_exceeded_target", report["results"][0]["latest_error"])

    def test_failed_event_status_fails_even_when_duration_is_fast(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_extra_changed",
                action_name="relation_extra_update",
                seconds=0.2,
                event_status="failed",
            )
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_relation_extra"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["results"][0]["failed_sample_count"], 1)

    def test_matching_reason_with_wrong_action_name_does_not_satisfy_profile(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_changed",
                action_name="confirm_relation",
            )
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_manual_closure_or_withdraw"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["results"][0]["status"], "missing")

    def test_workbench_relation_withdraw_profile_requires_cross_page_refresh_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
            _event(scope_type="tax_offset", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 9)

    def test_workbench_relation_confirm_profile_requires_canonical_relation_and_downstream_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
            _event(scope_type="tax_offset", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_confirm"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 9)

    def test_workbench_relation_bank_invoice_profile_excludes_cost_statistics(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
            _event(scope_type="tax_offset", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_confirm_bank_invoice"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 8)
        self.assertNotIn(
            "cost_statistics",
            {result["scope_type"] for result in report["results"]},
        )

    def test_workbench_relation_bank_invoice_withdraw_profile_excludes_cost_statistics(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
            _event(scope_type="tax_offset", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw_bank_invoice"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 8)
        self.assertNotIn(
            "cost_statistics",
            {result["scope_type"] for result in report["results"]},
        )

    def test_no_oa_withdraw_profile_requires_no_oa_and_cross_page_refresh_scopes(self) -> None:
        rows = [
            _event(
                scope_type="no_oa_bank_batch",
                reason="no_oa_bank_batch_changed",
                action_name="no_oa_bank_batch_withdraw",
            ),
            _event(
                scope_type="workbench",
                reason="workbench_scope_invalidated",
                action_name="no_oa_bank_batch_withdraw",
            ),
            _event(
                scope_type="workbench_relation",
                reason="no_oa_bank_batch_changed",
                action_name="no_oa_bank_batch_withdraw",
            ),
            _event(
                scope_type="cost_statistics",
                reason="no_oa_bank_batch_changed",
                action_name="no_oa_bank_batch_withdraw",
            ),
            _event(
                scope_type="search",
                reason="no_oa_bank_batch_changed",
                action_name="no_oa_bank_batch_withdraw",
            ),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["no_oa_bank_batch_withdraw"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 5)

    def test_unknown_operation_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown write-operation SLO profiles"):
            write_operation_slo_audit.audit_write_operation_slo(
                FakeConnection([]),
                operations=["does_not_exist"],
            )

    def test_since_filter_uses_explicit_event_created_lower_bound(self) -> None:
        since = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
        connection = FakeConnection(
            [
                _event(scope_type="workbench", reason="workbench_relation_changed"),
                _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
                _event(scope_type="bank_detail", reason="workbench_relation_changed"),
                _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
                _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
                _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
                _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
                _event(scope_type="search", reason="workbench_relation_changed"),
                _event(scope_type="tax_offset", reason="workbench_relation_changed"),
            ]
        )

        report = write_operation_slo_audit.audit_write_operation_slo(
            connection,
            operations=["workbench_relation_confirm"],
            since=since,
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["since"], since.isoformat())
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("e.created_at >= %s", sql)
        self.assertEqual(params, ("default", since, 2000))


if __name__ == "__main__":
    unittest.main()
