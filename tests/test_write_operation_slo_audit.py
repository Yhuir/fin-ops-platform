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
    event_type: str | None = None,
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
        "event_type": event_type or f"{scope_type}.read_model.refresh",
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
    def test_no_recent_write_samples_fail_instead_of_claiming_write_chain_closed(self) -> None:
        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection([]),
            operations=["turnover_manual_closure_or_withdraw"],
            target_ms=1_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["event_sample_count"], 0)
        self.assertEqual(report["expectation_count"], 5)
        self.assertEqual(report["missing_expectation_count"], 5)
        self.assertTrue(all(result["status"] == "missing" for result in report["results"]))

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

    def test_enqueue_duration_uses_available_at_instead_of_transaction_created_at(self) -> None:
        created_at = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)
        row = _event(
            scope_type="turnover_ledger",
            reason="turnover_relation_extra_changed",
            action_name="relation_extra_update",
            seconds=5.0,
        )
        row["created_at"] = created_at
        row["available_at"] = created_at + timedelta(seconds=4.5)
        row["processed_at"] = created_at + timedelta(seconds=5.0)
        row["updated_at"] = created_at + timedelta(seconds=5.0)

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection([row]),
            operations=["turnover_relation_extra"],
            target_ms=1_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["results"][0]["p95_enqueue_to_done_ms"], 500.0)

    def test_p99_long_tail_fails_even_when_p95_meets_one_second_target(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_extra_changed",
                action_name="relation_extra_update",
                seconds=0.8,
                event_id=f"fast-{index}",
            )
            for index in range(19)
        ]
        rows.append(
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_extra_changed",
                action_name="relation_extra_update",
                seconds=3.5,
                event_id="slow-tail",
            )
        )

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_relation_extra"],
            target_ms=1_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["p99_target_ms"], 3_000.0)
        result = report["results"][0]
        self.assertEqual(result["p95_enqueue_to_done_ms"], 800.0)
        self.assertEqual(result["p99_enqueue_to_done_ms"], 3500.0)
        self.assertIn("p99_enqueue_to_done_ms_exceeded_target", result["latest_error"])

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

    def test_recent_events_since_can_filter_by_operation_expectations_in_sql(self) -> None:
        connection = FakeConnection([])
        expectations = write_operation_slo_audit.selected_expectations_for_operations(
            ["turnover_manual_closure_or_withdraw"]
        )

        write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id="default",
            started_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc),
            limit=50,
            expectations=expectations,
        )

        sql, params = connection.fetch_all_calls[-1]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("e.event_type = %s", normalized_sql)
        self.assertIn("e.scope_type = %s", normalized_sql)
        self.assertIn("= any(%s)", normalized_sql)
        self.assertIn("turnover_ledger.read_model.refresh", params)
        self.assertIn("turnover_relation_changed", params)
        self.assertIn(
            [
                "turnover_relation_zero_difference_closure",
                "withdraw_relation",
                "turnover_relation_withdraw",
            ],
            params,
        )
        self.assertEqual(params[-1], 50)

    def test_committed_workbench_outbox_event_ids_returns_exact_unique_evidence(self) -> None:
        connection = FakeConnection(
            [
                {
                    "status": "committed",
                    "outbox_event_ids": ["event-1", "event-2"],
                }
            ]
        )

        event_ids = write_operation_slo_audit.committed_workbench_outbox_event_ids(
            connection,
            tenant_id="default",
            idempotency_key="phase20-confirm-1",
        )

        self.assertEqual(event_ids, ["event-1", "event-2"])
        sql, params = connection.fetch_all_calls[-1]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("from app.workbench_idempotency_records", normalized_sql)
        self.assertIn("tenant_id = %s", normalized_sql)
        self.assertIn("idempotency_key = %s", normalized_sql)
        self.assertEqual(params, ("default", "phase20-confirm-1"))

    def test_workbench_idempotency_evidence_exposes_only_durable_status_events_and_response(self) -> None:
        evidence = write_operation_slo_audit.workbench_idempotency_evidence(
            FakeConnection(
                [
                    {
                        "status": "committed",
                        "outbox_event_ids": ["event-1"],
                        "response_payload": {"turnover_relation": {"relation_id": "turnover-test-1"}},
                    }
                ]
            ),
            tenant_id="default",
            idempotency_key="phase20-confirm-1",
        )

        self.assertEqual(
            evidence,
            {
                "status": "committed",
                "outbox_event_ids": ["event-1"],
                "response_payload": {"turnover_relation": {"relation_id": "turnover-test-1"}},
            },
        )

        failed = write_operation_slo_audit.workbench_idempotency_evidence(
            FakeConnection([{"status": "failed", "outbox_event_ids": [], "response_payload": {}}]),
            tenant_id="default",
            idempotency_key="phase20-failed-1",
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["outbox_event_ids"], [])

    def test_committed_workbench_outbox_event_ids_fails_closed_on_missing_or_ambiguous_record(self) -> None:
        for rows in (
            [],
            [
                {"status": "committed", "outbox_event_ids": ["event-1"]},
                {"status": "committed", "outbox_event_ids": ["event-2"]},
            ],
        ):
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(ValueError, "exactly one Workbench idempotency record"):
                    write_operation_slo_audit.committed_workbench_outbox_event_ids(
                        FakeConnection(rows),
                        tenant_id="default",
                        idempotency_key="phase20-confirm-1",
                    )

    def test_committed_workbench_outbox_event_ids_fails_closed_on_invalid_record_evidence(self) -> None:
        invalid_rows = (
            {"status": "reserved", "outbox_event_ids": ["event-1"]},
            {"status": "committed", "outbox_event_ids": []},
            {"status": "committed", "outbox_event_ids": ["event-1", "event-1"]},
            {"status": "committed", "outbox_event_ids": [""]},
            {"status": "committed", "outbox_event_ids": "event-1"},
        )

        for row in invalid_rows:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    write_operation_slo_audit.committed_workbench_outbox_event_ids(
                        FakeConnection([row]),
                        tenant_id="default",
                        idempotency_key="phase20-confirm-1",
                    )

    def test_recent_events_since_filters_by_exact_event_ids_without_weakening_other_boundaries(self) -> None:
        connection = FakeConnection([])
        expectations = write_operation_slo_audit.selected_expectations_for_operations(
            ["workbench_relation_confirm_bank_invoice_cross_page"]
        )
        started_at = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)

        write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id="default",
            started_at=started_at,
            limit=50,
            expectations=expectations,
            event_ids=["event-1", "event-2"],
        )

        sql, params = connection.fetch_all_calls[-1]
        normalized_sql = " ".join(sql.lower().split())
        self.assertIn("e.tenant_id = %s", normalized_sql)
        self.assertNotIn("e.created_at >= %s", normalized_sql)
        self.assertNotIn("e.event_type = %s", normalized_sql)
        self.assertIn("e.id::text = any(%s)", normalized_sql)
        self.assertEqual(params[0], "default")
        self.assertEqual(params[-2], ["event-1", "event-2"])
        self.assertEqual(params[-1], 50)

        write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id="default",
            started_at=started_at,
            limit=50,
            expectations=expectations,
        )
        fallback_sql, fallback_params = connection.fetch_all_calls[-1]
        self.assertIn("e.created_at >= %s", " ".join(fallback_sql.lower().split()))
        self.assertEqual(fallback_params[0:2], ("default", started_at))
        self.assertIn("e.event_type = %s", " ".join(fallback_sql.lower().split()))

        with self.assertRaisesRegex(ValueError, "sequence of strings"):
            write_operation_slo_audit.recent_read_model_refresh_events_since(
                connection,
                tenant_id="default",
                started_at=started_at,
                limit=50,
                expectations=expectations,
                event_ids="event-1",
            )

    def test_workbench_relation_withdraw_profile_requires_operation_visible_workbench_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed", seconds=3.0),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw"],
            target_ms=2_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 2)
        self.assertEqual(
            {result["scope_type"] for result in report["results"]},
            {"workbench", "workbench_relation"},
        )

    def test_workbench_relation_withdraw_profile_fails_when_workbench_refresh_is_slow(self) -> None:
        rows = [
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="workbench", reason="workbench_relation_changed", seconds=12.0),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw"],
            target_ms=2_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["expectation_count"], 2)
        self.assertIn(
            "workbench",
            {result["scope_type"] for result in report["results"] if result["status"] == "fail"},
        )

    def test_workbench_relation_withdraw_cross_page_profile_keeps_background_refresh_visible(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="output_invoice_collection", reason="workbench_relation_changed"),
            _event(scope_type="oa_pending_payment", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw_cross_page"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 10)

    def test_workbench_relation_confirm_profile_requires_operation_visible_workbench_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed", seconds=3.0),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_confirm"],
            target_ms=2_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 2)
        self.assertEqual(
            {result["scope_type"] for result in report["results"]},
            {"workbench", "workbench_relation"},
        )

    def test_workbench_relation_confirm_cross_page_profile_keeps_background_refresh_visible(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="output_invoice_collection", reason="workbench_relation_changed"),
            _event(scope_type="oa_pending_payment", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_confirm_cross_page"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 10)

    def test_full_cross_page_profiles_require_oa_pending_payment_refresh(self) -> None:
        for operation in (
            "workbench_relation_confirm_cross_page",
            "workbench_relation_withdraw_cross_page",
        ):
            with self.subTest(operation=operation):
                expectations = write_operation_slo_audit.selected_expectations_for_operations([operation])
                oa_expectation = next(
                    expectation for expectation in expectations if expectation.scope_type == "oa_pending_payment"
                )
                self.assertTrue(oa_expectation.required)
                self.assertEqual(oa_expectation.reason, "workbench_relation_changed")

    def test_workbench_relation_bank_invoice_cross_page_profile_includes_real_cost_fanout(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="output_invoice_collection", reason="workbench_relation_changed"),
            _event(scope_type="oa_pending_payment", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_confirm_bank_invoice_cross_page"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 10)
        self.assertIn(
            "cost_statistics",
            {result["scope_type"] for result in report["results"]},
        )

    def test_workbench_relation_bank_invoice_withdraw_cross_page_profile_includes_real_cost_fanout(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="output_invoice_collection", reason="workbench_relation_changed"),
            _event(scope_type="oa_pending_payment", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["workbench_relation_withdraw_bank_invoice_cross_page"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 10)
        self.assertIn(
            "cost_statistics",
            {result["scope_type"] for result in report["results"]},
        )

    def test_turnover_relation_withdraw_cross_page_profile_matches_real_closure_fanout(self) -> None:
        rows = [
            _event(
                scope_type="turnover_ledger",
                reason="turnover_relation_changed",
                action_name="turnover_relation_withdraw",
            ),
            _event(
                scope_type="workbench", reason="turnover_relation_changed", action_name="turnover_relation_withdraw"
            ),
            _event(
                scope_type="workbench_relation",
                reason="turnover_relation_changed",
                action_name="turnover_relation_withdraw",
            ),
            _event(
                scope_type="cost_statistics",
                reason="turnover_relation_changed",
                action_name="turnover_relation_withdraw",
            ),
            _event(scope_type="search", reason="turnover_relation_changed", action_name="turnover_relation_withdraw"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["turnover_relation_withdraw_cross_page"],
            target_ms=5_000,
        )

        scope_types = {result["scope_type"] for result in report["results"]}
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 5)
        self.assertEqual(
            scope_types,
            {"turnover_ledger", "workbench", "workbench_relation", "cost_statistics", "search"},
        )
        self.assertNotIn("invoice_lifecycle", scope_types)
        self.assertNotIn("input_invoice_usage", scope_types)
        self.assertNotIn("tax_offset", scope_types)

    def test_turnover_relation_confirm_cross_page_profile_matches_withdraw_scope_contract(self) -> None:
        confirm_scopes = {
            expectation.scope_type
            for expectation in write_operation_slo_audit.selected_expectations_for_operations(
                ["turnover_relation_confirm_cross_page"]
            )
        }
        withdraw_scopes = {
            expectation.scope_type
            for expectation in write_operation_slo_audit.selected_expectations_for_operations(
                ["turnover_relation_withdraw_cross_page"]
            )
        }

        self.assertEqual(confirm_scopes, withdraw_scopes)
        self.assertEqual(
            confirm_scopes,
            {"turnover_ledger", "workbench", "workbench_relation", "cost_statistics", "search"},
        )

    def test_pending_invoice_attach_existing_profile_requires_cross_page_refresh_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["pending_invoice_attach_existing_invoice"],
            target_ms=5_000,
        )

        scope_types = {result["scope_type"] for result in report["results"]}
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 7)
        self.assertEqual(
            scope_types,
            {
                "workbench",
                "workbench_relation",
                "bank_detail",
                "invoice_lifecycle",
                "pending_invoice",
                "input_invoice_usage",
                "search",
            },
        )

    def test_pending_invoice_attach_existing_with_oa_profile_includes_oa_and_cost_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="invoice_lifecycle", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="input_invoice_usage", reason="workbench_relation_changed"),
            _event(scope_type="oa_pending_payment", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["pending_invoice_attach_existing_invoice_with_oa"],
            target_ms=5_000,
        )

        scope_types = {result["scope_type"] for result in report["results"]}
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 9)
        self.assertIn("oa_pending_payment", scope_types)
        self.assertIn("cost_statistics", scope_types)

    def test_bank_flow_rule_batch_submit_profile_requires_current_page_and_relation_visibility_scopes(self) -> None:
        rows = [
            _event(scope_type="bank_flow_rule_batch", reason="workbench_relation_changed"),
            _event(scope_type="workbench", reason="workbench_relation_changed"),
            _event(scope_type="workbench_relation", reason="workbench_pair_relation_changed"),
            _event(scope_type="bank_detail", reason="workbench_relation_changed"),
            _event(scope_type="pending_invoice", reason="workbench_relation_changed"),
            _event(scope_type="cost_statistics", reason="workbench_relation_changed"),
            _event(scope_type="search", reason="workbench_relation_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_flow_rule_batch_submit"],
            target_ms=5_000,
        )

        scope_types = {result["scope_type"] for result in report["results"]}
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 7)
        self.assertEqual(
            scope_types,
            {
                "bank_flow_rule_batch",
                "workbench",
                "workbench_relation",
                "bank_detail",
                "pending_invoice",
                "cost_statistics",
                "search",
            },
        )
        self.assertNotIn("no_oa_bank_batch", scope_types)

    def test_pairing_write_profiles_require_canonical_workbench_relation_refresh(self) -> None:
        pairing_operations = [
            "turnover_manual_closure_or_withdraw",
            "workbench_relation_confirm_cross_page",
            "workbench_relation_withdraw_cross_page",
            "workbench_relation_confirm_bank_invoice_cross_page",
            "workbench_relation_withdraw_bank_invoice_cross_page",
            "turnover_relation_confirm_cross_page",
            "turnover_relation_withdraw_cross_page",
            "pending_invoice_attach_existing_invoice",
            "pending_invoice_attach_existing_invoice_with_oa",
            "bank_flow_rule_batch_submit",
        ]

        for operation in pairing_operations:
            with self.subTest(operation=operation):
                scope_types = {
                    expectation.scope_type
                    for expectation in write_operation_slo_audit.selected_expectations_for_operations([operation])
                }
                self.assertIn("workbench_relation", scope_types)
                self.assertIn("workbench", scope_types)

    def test_invoice_import_confirmed_profile_requires_actual_file_import_refresh_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="tax_offset", reason="invoice_file_import_confirm"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["invoice_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 10)
        self.assertEqual(report["failed_expectation_count"], 0)
        self.assertEqual(
            {result["scope_type"] for result in report["results"]},
            {
                "workbench",
                "workbench_relation",
                "invoice_lifecycle",
                "search",
                "pending_invoice",
                "input_invoice_usage",
                "output_invoice_collection",
                "oa_pending_payment",
                "cost_statistics",
                "tax_offset",
            },
        )

    def test_invoice_import_confirmed_profile_fails_when_downstream_scope_is_missing(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="tax_offset", reason="invoice_file_import_confirm"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["invoice_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_expectation_count"], 1)
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(missing[0]["scope_type"], "cost_statistics")
        self.assertEqual(missing[0]["reason"], "import_state_changed")

    def test_invoice_import_confirmed_profile_allows_direction_specific_relation_refresh(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="tax_offset", reason="invoice_file_import_confirm"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["invoice_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        skipped = [result for result in report["results"] if result["status"] == "skipped"]
        self.assertEqual([result["scope_type"] for result in skipped], ["output_invoice_collection"])
        self.assertEqual(report["missing_expectation_count"], 0)

    def test_bank_import_confirmed_profile_requires_import_state_refresh_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="bank_account_balance", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="bank_detail", reason="import_facts_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 11)
        bank_detail_result = next(result for result in report["results"] if result["scope_type"] == "bank_detail")
        self.assertEqual(bank_detail_result["event_type"], "bank_detail.read_model.refresh")

    def test_bank_import_confirmed_profile_fails_when_cost_scope_is_missing(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="bank_account_balance", reason="import_state_changed"),
            _event(scope_type="bank_detail", reason="import_facts_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_expectation_count"], 1)
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(missing[0]["scope_type"], "cost_statistics")
        self.assertEqual(missing[0]["reason"], "import_state_changed")

    def test_bank_import_confirmed_profile_allows_skipped_invoice_direction_pages(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="bank_account_balance", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="bank_detail", reason="import_facts_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        skipped = [result for result in report["results"] if result["status"] == "skipped"]
        self.assertEqual(
            [result["scope_type"] for result in skipped],
            ["input_invoice_usage", "output_invoice_collection"],
        )
        self.assertEqual(report["missing_expectation_count"], 0)

    def test_bank_import_confirmed_profile_fails_when_account_balance_scope_is_missing(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="bank_detail", reason="import_facts_changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_expectation_count"], 1)
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(missing[0]["scope_type"], "bank_account_balance")
        self.assertEqual(missing[0]["reason"], "import_state_changed")

    def test_bank_import_confirmed_profile_requires_real_bank_detail_refresh_not_import_fact_ack(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="import_state_changed"),
            _event(scope_type="workbench_relation", reason="import_state_changed"),
            _event(scope_type="invoice_lifecycle", reason="import_state_changed"),
            _event(scope_type="search", reason="import_state_changed"),
            _event(scope_type="pending_invoice", reason="import_state_changed"),
            _event(scope_type="input_invoice_usage", reason="import_state_changed"),
            _event(scope_type="output_invoice_collection", reason="import_state_changed"),
            _event(scope_type="oa_pending_payment", reason="import_state_changed"),
            _event(scope_type="bank_account_balance", reason="import_state_changed"),
            _event(scope_type="cost_statistics", reason="import_state_changed"),
            _event(scope_type="bank_detail", reason="import_facts_changed", event_type="import.fact.changed"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["scope_type"], "bank_detail")
        self.assertEqual(missing[0]["event_type"], "bank_detail.read_model.refresh")

    def test_etc_import_confirmed_profile_requires_derived_lifecycle_refresh_scopes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="etc_invoice_import_confirm"),
            _event(scope_type="workbench_relation", reason="etc_invoice_import_confirm"),
            _event(scope_type="invoice_lifecycle", reason="etc_invoice_import_confirm"),
            _event(scope_type="tax_offset", reason="etc_invoice_import_confirm"),
            _event(scope_type="cost_statistics", reason="etc_invoice_import_confirm"),
            _event(scope_type="search", reason="etc_invoice_import_confirm"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["etc_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["expectation_count"], 5)
        self.assertNotIn("search", {result["scope_type"] for result in report["results"]})

    def test_etc_import_confirmed_profile_fails_when_tax_scope_is_missing(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="etc_invoice_import_confirm"),
            _event(scope_type="workbench_relation", reason="etc_invoice_import_confirm"),
            _event(scope_type="invoice_lifecycle", reason="etc_invoice_import_confirm"),
            _event(scope_type="cost_statistics", reason="etc_invoice_import_confirm"),
        ]

        report = write_operation_slo_audit.audit_write_operation_slo(
            FakeConnection(rows),
            operations=["etc_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["missing_expectation_count"], 1)
        missing = [result for result in report["results"] if result["status"] == "missing"]
        self.assertEqual(missing[0]["scope_type"], "tax_offset")
        self.assertEqual(missing[0]["reason"], "etc_invoice_import_confirm")

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

    def test_query_joins_import_fact_dirty_scope_with_default_source_version(self) -> None:
        connection = FakeConnection([])

        report = write_operation_slo_audit.audit_write_operation_slo(
            connection,
            operations=["bank_import_confirmed"],
            target_ms=5_000,
        )

        self.assertEqual(report["status"], "fail")
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("e.event_type = 'import.fact.changed'", sql)
        self.assertIn("d.source_version = coalesce(e.source_version, 0)", sql)
        self.assertEqual(params, ("default", 24.0, 2000))


if __name__ == "__main__":
    unittest.main()
