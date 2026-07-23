from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from fin_ops_platform.tools import write_operation_slo_audit


class RecordingConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append((sql, params))
        return list(self.rows)


def _event(
    *,
    scope_type: str = "workbench",
    reason: str = "workbench_relation_changed",
    action_name: str = "",
) -> dict[str, object]:
    created_at = datetime(2026, 7, 22, tzinfo=UTC)
    return {
        "event_id": "event-1",
        "event_type": f"{scope_type}.read_model.refresh",
        "scope_type": scope_type,
        "scope_key": "2026-07",
        "reason": reason,
        "action_name": action_name,
        "event_status": "done",
        "dirty_status": "done",
        "available_at": created_at,
        "processed_at": created_at + timedelta(milliseconds=20),
    }


class WriteOperationSloAuditTests(unittest.TestCase):
    def test_no_legacy_write_refresh_is_a_pass(self) -> None:
        connection = RecordingConnection([])

        report = write_operation_slo_audit.audit_write_operation_slo(
            connection,
            operations=["workbench_relation_confirm"],
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["event_sample_count"], 0)
        self.assertTrue(report["results"])
        self.assertTrue(all(result["forbidden"] for result in report["results"]))
        self.assertTrue(all(result["status"] == "pass" for result in report["results"]))

    def test_matching_legacy_write_refresh_fails_zero_fanout_contract(self) -> None:
        expectation = write_operation_slo_audit.OperationExpectation(
            "test_operation",
            "workbench",
            "workbench_relation_changed",
        )

        result = write_operation_slo_audit.evaluate_operation_expectations(
            [_event()],
            expectations=[expectation],
            target_ms=1_000,
        )[0]

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.sample_count, 1)
        self.assertEqual(result.latest_error, "forbidden_write_time_read_model_fan_out_detected")

    def test_unrelated_access_refresh_does_not_match_write_profile(self) -> None:
        expectation = write_operation_slo_audit.OperationExpectation(
            "test_operation",
            "workbench",
            "workbench_relation_changed",
        )

        result = write_operation_slo_audit.evaluate_operation_expectations(
            [_event(reason="api_source_versions_stale")],
            expectations=[expectation],
            target_ms=1_000,
        )[0]

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.sample_count, 0)

    def test_recent_event_query_excludes_deleted_import_fact_bridge(self) -> None:
        connection = RecordingConnection([])

        write_operation_slo_audit.recent_read_model_refresh_events_since(
            connection,
            tenant_id="default",
            started_at=datetime(2026, 7, 22, tzinfo=UTC),
            limit=100,
            expectations=write_operation_slo_audit.selected_expectations_for_operations(
                ["bank_import_confirmed"]
            ),
        )

        sql = connection.calls[0][0]
        self.assertIn("e.event_type like '%%.read_model.refresh'", sql)
        self.assertNotIn("import.fact.changed", sql)
        self.assertIn("e.event_type = %s", sql)

    def test_committed_idempotency_receipt_allows_zero_outbox_events(self) -> None:
        connection = RecordingConnection(
            [{"status": "committed", "outbox_event_ids": [], "response_payload": {"ok": True}}]
        )

        evidence = write_operation_slo_audit.workbench_idempotency_evidence(
            connection,
            tenant_id="default",
            idempotency_key="fixture-1",
        )

        self.assertEqual(evidence["outbox_event_ids"], [])
        self.assertEqual(
            write_operation_slo_audit.committed_workbench_outbox_event_ids(
                connection,
                tenant_id="default",
                idempotency_key="fixture-1",
            ),
            [],
        )

    def test_unknown_operation_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown write-operation"):
            write_operation_slo_audit.selected_expectations_for_operations(["unknown"])

    def test_explicit_access_expectation_can_still_measure_completion_latency(self) -> None:
        expectation = write_operation_slo_audit.OperationExpectation(
            "access_probe",
            "workbench",
            "api_source_versions_stale",
            forbidden=False,
        )

        result = write_operation_slo_audit.evaluate_operation_expectations(
            [_event(reason="api_source_versions_stale")],
            expectations=[expectation],
            target_ms=1_000,
        )[0]

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.p95_enqueue_to_done_ms, 20.0)


if __name__ == "__main__":
    unittest.main()
