from __future__ import annotations

import unittest
from unittest.mock import patch

from fin_ops_platform.tools import runtime_sync_closure_gate as gate


def clean_rabbitmq_queues() -> dict[str, dict[str, object]]:
    return {
        event_type: {
            "queue": f"finops.{event_type}",
            "messages": 0,
            "unacked": 0,
            "consumers": 1,
            "dead_letter_messages": 0,
        }
        for event_type in gate.rabbitmq_dispatch_event_types()
    }


class FakeRuntimeMonitoringRepository:
    def __init__(self, _connection) -> None:
        pass

    def ready_health_summary(self) -> dict[str, object]:
        return {
            "queue_backlog": {},
            "dirty_scopes": {},
            "failed_jobs": 0,
            "rabbitmq_unpublished_backlog": 0,
            "rabbitmq_publishing_backlog": 0,
            "rabbitmq_publish_failed_backlog": 0,
            "stale_dirty_scope_count": 0,
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 0,
            "worker_metrics": [
                {"worker_kind": "workbench", "status": "ok", "required": True}
            ],
            "rabbitmq_management_configured": True,
            "rabbitmq_queue_depth": 0,
            "rabbitmq_unacked_messages": 0,
            "rabbitmq_dlq_count": 0,
            "rabbitmq_queues": clean_rabbitmq_queues(),
        }


class FakeRuntimeQueueRepository:
    def __init__(self, _connection) -> None:
        pass

    def reconcile_completed_publish_states(self) -> int:
        return 0


class EmptyRuntimeMonitoringRepository:
    def __init__(self, _connection) -> None:
        pass

    def ready_health_summary(self) -> dict[str, object]:
        return {}


class BackloggedRabbitMqRuntimeMonitoringRepository:
    def __init__(self, _connection) -> None:
        pass

    def ready_health_summary(self) -> dict[str, object]:
        summary = FakeRuntimeMonitoringRepository(None).ready_health_summary()
        queues = summary["rabbitmq_queues"]
        assert isinstance(queues, dict)
        summary["rabbitmq_queue_depth"] = 1
        queues["no_oa_bank_batch.read_model.refresh"] = {
            "queue": "finops.no_oa_bank_batch.read_model.refresh",
            "messages": 1,
            "unacked": 0,
            "consumers": 1,
            "dead_letter_messages": 0,
        }
        return summary


class TerminalPublishRace:
    def __init__(self) -> None:
        self.publishing = 0
        self.reconciliations = 0
        self.samples = 0


class TerminalPublishRaceQueueRepository:
    def __init__(self, connection: TerminalPublishRace) -> None:
        self._connection = connection

    def reconcile_completed_publish_states(self) -> int:
        self._connection.reconciliations += 1
        reconciled = self._connection.publishing
        self._connection.publishing = 0
        return reconciled


class TerminalPublishRaceMonitoringRepository:
    def __init__(self, connection: TerminalPublishRace) -> None:
        self._connection = connection

    def ready_health_summary(self) -> dict[str, object]:
        self._connection.samples += 1
        if self._connection.samples == 1:
            self._connection.publishing = 1
        summary = FakeRuntimeMonitoringRepository(None).ready_health_summary()
        summary["rabbitmq_publishing_backlog"] = self._connection.publishing
        return summary


class RecurrentTerminalPublishRaceQueueRepository:
    def __init__(self, connection: TerminalPublishRace) -> None:
        self._connection = connection

    def reconcile_completed_publish_states(self) -> int:
        self._connection.reconciliations += 1
        return 1


class FakeWriteTransaction:
    def __init__(self) -> None:
        self.marker: str | None = None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert"):
            self.marker = str(params[0])
            return 1
        if normalized.startswith("delete"):
            deleted = int(self.marker == str(params[0]))
            self.marker = None
            return deleted
        return 0

    def fetch_one(
        self,
        _sql: str,
        params: tuple[object, ...],
    ) -> dict[str, object] | None:
        return {"marker": self.marker} if self.marker == str(params[0]) else None


class FakeTransactionContext:
    def __init__(self, transaction: FakeWriteTransaction) -> None:
        self.transaction = transaction

    def __enter__(self) -> FakeWriteTransaction:
        return self.transaction

    def __exit__(self, *_args: object) -> None:
        return None


class FakeWriteConnection:
    def __init__(self) -> None:
        self.transaction_value = FakeWriteTransaction()

    def transaction(self) -> FakeTransactionContext:
        return FakeTransactionContext(self.transaction_value)


def read_model_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "planned_scope_count": 1,
        "result_count": 1,
        "failed_count": 0,
        "results": [
            {
                "status": "pass",
                "read_model_key": "workbench",
                "scope_type": "workbench",
                "scope_key": "all",
                "enqueue_to_fresh_ms": 500.0,
            }
        ],
    }


def http_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "auth_configured": True,
        "summary": {"probe_count": 1, "sample_count": 3, "failed_probe_count": 0},
        "probes": [
            {
                "name": "workbench_groups_all_paired",
                "status": "pass",
                "sample_count": 3,
                "success_count": 3,
            }
        ],
    }


def sse_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "auth_configured": True,
        "summary": {
            "probe_count": 1,
            "failed_probe_count": 0,
            "max_first_event_ms": 500.0,
        },
        "probes": [
            {
                "name": "workbench_events_all",
                "status": "pass",
                "first_event_ms": 500.0,
                "event_names": ["workbench.read_model.completed"],
            }
        ],
    }


def health_ready_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "url": "https://example.test/fin-ops-api/health/ready",
        "elapsed_ms": 120.0,
        "response_bytes": 8_000,
        "health_status": "ready",
        "api_performance_endpoints_returned": 20,
        "api_performance_endpoint_count": 25,
        "api_performance_omitted_endpoint_count": 5,
        "errors": [],
    }


def write_audit_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "event_sample_count": 13,
        "expectation_count": 13,
        "failed_expectation_count": 0,
        "missing_expectation_count": 0,
        "results": [],
    }


class ReleaseGateBoundaryTests(unittest.TestCase):
    def test_postgres_reversible_write_uses_isolated_temp_table(self) -> None:
        check = gate._postgres_reversible_write_check(
            FakeWriteConnection(),
            target_ms=1_000,
        )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(check.payload["isolation"], "pg_temp")
        self.assertEqual(check.payload["rows_inserted"], 1)
        self.assertEqual(check.payload["rows_deleted"], 1)
        self.assertEqual(check.payload["residue_count"], 0)

    def test_postgres_reversible_write_fails_closed(self) -> None:
        class BrokenConnection:
            def transaction(self):
                raise RuntimeError("database unavailable")

        check = gate._postgres_reversible_write_check(
            BrokenConnection(),
            target_ms=1_000,
        )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["isolation"], "pg_temp")
        self.assertEqual(check.payload["error"], "database unavailable")

    def test_page_canonical_audit_requires_authentication(self) -> None:
        check = gate._page_canonical_audit_check(
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={},
            timeout_seconds=1,
            poll_interval_seconds=0.05,
            require_auth=True,
        )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["error"], "auth_required")

    def test_page_canonical_audit_uses_read_only_snapshot_evidence(self) -> None:
        audit = {
            "status": "pass",
            "system_audit_id": "system-audit:test",
            "snapshot_identity": "snapshot:test",
            "external_evidence": "pass",
        }
        with patch.object(
            gate.write_operation_e2e_smoke,
            "_wait_for_system_audit",
            return_value=audit,
        ) as wait_for_audit:
            check = gate._page_canonical_audit_check(
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(check.payload["audit_count"], 1)
        self.assertEqual(check.payload["system_audits"], [audit])
        wait_for_audit.assert_called_once()


class RuntimeSyncClosureGateTests(unittest.TestCase):
    def setUp(self) -> None:
        patchers = [
            patch.object(gate, "RuntimeQueueRepository", FakeRuntimeQueueRepository),
            patch.object(
                gate.health_ready_payload_probe,
                "collect_health_ready_payload",
                return_value=health_ready_pass_report(),
            ),
            patch.object(
                gate,
                "_postgres_reversible_write_check",
                return_value=gate.ClosureCheck(
                    "postgres_reversible_write",
                    gate.PASS,
                    "pass",
                    {"isolation": "pg_temp"},
                ),
            ),
            patch.object(
                gate,
                "_page_canonical_audit_check",
                return_value=gate.ClosureCheck(
                    "page_canonical_audit",
                    gate.PASS,
                    "pass",
                    {"status": "pass", "audit_count": 1},
                ),
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_active_dirty_scope_prevents_runtime_closure(self) -> None:
        blockers = gate._runtime_blockers(
            {
                "dirty_scopes": {"cost_statistics": 1},
                "queue_backlog": {},
                "rabbitmq_management_configured": True,
            }
        )

        self.assertEqual(blockers, {"dirty_scopes": {"cost_statistics": 1}})

    def test_missing_rabbitmq_management_metrics_prevents_runtime_closure(self) -> None:
        blockers = gate._runtime_blockers(
            {
                "queue_backlog": {},
                "dirty_scopes": {},
                "rabbitmq_management_configured": False,
            }
        )

        self.assertEqual(blockers, {"rabbitmq_management_configured": False})

    def test_runtime_blockers_require_every_dispatch_queue_consumer(self) -> None:
        summary = FakeRuntimeMonitoringRepository(None).ready_health_summary()
        event_types = gate.rabbitmq_dispatch_event_types()
        queues = summary["rabbitmq_queues"]
        assert isinstance(queues, dict)
        queues.pop(event_types[0])
        metrics = queues[event_types[1]]
        assert isinstance(metrics, dict)
        metrics["consumers"] = 0

        blockers = gate._runtime_blockers(summary)

        self.assertEqual(blockers["rabbitmq_queue_metrics_missing"], [event_types[0]])
        self.assertEqual(
            blockers["rabbitmq_queues_without_consumers"],
            [event_types[1]],
        )

    def test_runtime_blockers_reject_all_durable_publish_backlogs(self) -> None:
        summary = FakeRuntimeMonitoringRepository(None).ready_health_summary()
        summary["rabbitmq_unpublished_backlog"] = 1
        summary["rabbitmq_publishing_backlog"] = 2
        summary["rabbitmq_publish_failed_backlog"] = 3

        blockers = gate._runtime_blockers(summary)

        self.assertEqual(blockers["rabbitmq_unpublished_backlog"], 1)
        self.assertEqual(blockers["rabbitmq_publishing_backlog"], 2)
        self.assertEqual(blockers["rabbitmq_publish_failed_backlog"], 3)

    def test_rejects_unknown_gate_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported release gate profile"):
            gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                profile="unknown",
            )

    def test_preflight_is_isolated_write_plus_read_only_runtime_gate(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(gate.read_model_slo_smoke, "run_smoke") as read_model_smoke, patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
        ) as http_slo, patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
        ) as sse_smoke, patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
        ) as write_audit, patch.object(
            gate.write_operation_e2e_smoke,
            "run_write_operation_e2e_smoke",
        ) as business_write_e2e:
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                profile="preflight",
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            [
                "postgres_reversible_write",
                "runtime_health",
                "health_ready_payload",
                "page_canonical_audit",
            ],
        )
        read_model_smoke.assert_not_called()
        http_slo.assert_not_called()
        sse_smoke.assert_not_called()
        write_audit.assert_not_called()
        business_write_e2e.assert_not_called()

    def test_runtime_health_empty_summary_prevents_closure_pass(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            EmptyRuntimeMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                object(),
                timeout_seconds=0,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["error"], "runtime_health_missing_facts")
        self.assertIn("queue_backlog", check.payload["missing_fields"])

    def test_runtime_health_preserves_per_queue_diagnostics(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            BackloggedRabbitMqRuntimeMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                object(),
                timeout_seconds=0,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(check.status, gate.FAIL)
        queue = check.payload["snapshot"]["rabbitmq_queues"]
        self.assertEqual(
            queue["no_oa_bank_batch.read_model.refresh"]["messages"],
            1,
        )

    def test_runtime_health_reconciles_terminal_publish_race(self) -> None:
        connection = TerminalPublishRace()
        with patch.object(
            gate,
            "RuntimeQueueRepository",
            TerminalPublishRaceQueueRepository,
        ), patch.object(
            gate,
            "RuntimeMonitoringRepository",
            TerminalPublishRaceMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                connection,
                timeout_seconds=1,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(connection.samples, 3)
        self.assertEqual(connection.reconciliations, 3)
        self.assertEqual(check.payload["reconciled_completed_publish_states"], 1)
        self.assertEqual(check.payload["clean_samples_after_reconciliation"], 1)
        self.assertIs(check.payload["terminal_publish_reconciliation_stable"], True)

    def test_runtime_health_rejects_continuously_recreated_terminal_publish_race(
        self,
    ) -> None:
        connection = TerminalPublishRace()
        with patch.object(
            gate,
            "RuntimeQueueRepository",
            RecurrentTerminalPublishRaceQueueRepository,
        ), patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                connection,
                timeout_seconds=0,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertIn(
            "terminal_publish_reconciliation_not_stable",
            check.payload["blockers"],
        )
        self.assertIs(check.payload["terminal_publish_reconciliation_stable"], False)

    def test_full_gate_passes_without_automatic_business_mutation(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value=read_model_pass_report(),
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value=http_pass_report(),
        ), patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value=sse_pass_report(),
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            return_value=write_audit_pass_report(),
        ), patch.object(
            gate.write_operation_e2e_smoke,
            "run_write_operation_e2e_smoke",
        ) as business_write_e2e:
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
                apply_read_model_smoke=True,
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            [
                "postgres_reversible_write",
                "read_model_direct_smoke",
                "authenticated_http_slo",
                "sse_first_event_smoke",
                "health_ready_payload",
                "write_operation_audit",
                "runtime_health_before_final_convergence",
                "runtime_health",
                "page_canonical_audit",
            ],
        )
        business_write_e2e.assert_not_called()

    def test_gate_fails_without_authenticated_read_only_evidence(self) -> None:
        with patch.object(
            gate,
            "_page_canonical_audit_check",
            return_value=gate.ClosureCheck(
                "page_canonical_audit",
                gate.FAIL,
                "auth required",
                {"error": "auth_required"},
            ),
        ), patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value={"status": "dry_run", "planned_scope_count": 14},
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value={
                "status": "auth_missing",
                "auth_configured": False,
                "summary": {"probe_count": 0, "sample_count": 0},
            },
        ), patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value={
                "status": "auth_missing",
                "auth_configured": False,
                "summary": {"probe_count": 0},
            },
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            return_value=write_audit_pass_report(),
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={},
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("page_canonical_audit", report["failed_checks"])
        self.assertIn("read_model_direct_smoke", report["failed_checks"])
        self.assertIn("authenticated_http_slo", report["failed_checks"])
        self.assertIn("sse_first_event_smoke", report["failed_checks"])
        self.assertFalse(report["auth_configured"])

    def test_gate_passes_admin_headers_to_http_and_canonical_audit(self) -> None:
        captured_http: dict[str, object] = {}
        captured_audit: dict[str, object] = {}

        def collect_http(**kwargs):
            captured_http.update(kwargs)
            return http_pass_report()

        def collect_audit(**kwargs):
            captured_audit.update(kwargs)
            return gate.ClosureCheck(
                "page_canonical_audit",
                gate.PASS,
                "pass",
                {"status": "pass", "audit_count": 1},
            )

        with patch.object(
            gate,
            "_page_canonical_audit_check",
            side_effect=collect_audit,
        ), patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value=read_model_pass_report(),
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            side_effect=collect_http,
        ), patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value=sse_pass_report(),
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            return_value=write_audit_pass_report(),
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer user"},
                admin_headers={"Cookie": "Admin-Token=admin"},
                apply_read_model_smoke=True,
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(captured_http["admin_headers"], {"Cookie": "Admin-Token=admin"})
        self.assertEqual(captured_audit["headers"], {"Cookie": "Admin-Token=admin"})

    def test_empty_probe_and_audit_samples_fail_closed(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value={
                "status": "pass",
                "planned_scope_count": 0,
                "result_count": 0,
                "results": [],
            },
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value={
                "status": "pass",
                "summary": {"probe_count": 0, "sample_count": 0},
                "probes": [],
            },
        ), patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value={
                "status": "pass",
                "summary": {"probe_count": 0},
                "probes": [],
            },
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            return_value={
                "status": "pass",
                "event_sample_count": 0,
                "expectation_count": 0,
                "results": [],
            },
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
                apply_read_model_smoke=True,
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("read_model_direct_smoke", report["failed_checks"])
        self.assertIn("authenticated_http_slo", report["failed_checks"])
        self.assertIn("sse_first_event_smoke", report["failed_checks"])
        self.assertIn("write_operation_audit", report["failed_checks"])

    def test_write_audit_uses_recent_real_operations_without_scenario_filter(self) -> None:
        calls: list[dict[str, object]] = []

        def audit_stub(_connection, **kwargs):
            calls.append(dict(kwargs))
            return write_audit_pass_report()

        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value=read_model_pass_report(),
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value=http_pass_report(),
        ), patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value=sse_pass_report(),
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            side_effect=audit_stub,
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
                apply_read_model_smoke=True,
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertIsNone(calls[0]["operations"])

    def test_health_ready_failure_prevents_closure(self) -> None:
        with patch.object(
            gate.health_ready_payload_probe,
            "collect_health_ready_payload",
            return_value={
                "status": "fail",
                "elapsed_ms": 2_000,
                "errors": ["health_ready_payload_slo_miss"],
            },
        ), patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                profile="preflight",
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("health_ready_payload", report["failed_checks"])

    def test_sse_failure_preserves_diagnostics(self) -> None:
        with patch.object(
            gate.sse_smoke_probe,
            "collect_sse_smoke",
            return_value={
                "status": "fail",
                "auth_configured": True,
                "summary": {"probe_count": 1, "failed_probe_count": 1},
                "probes": [
                    {
                        "name": "workbench_events_all",
                        "status": "fail",
                        "first_event_ms": 1_500.0,
                        "errors": ["sse_first_event_slo_miss"],
                    }
                ],
            },
        ):
            check = gate._sse_smoke_check(
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                target_ms=1_000,
                timeout_seconds=1,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(
            check.payload["failed_probes"][0]["errors"],
            ["sse_first_event_slo_miss"],
        )

    def test_http_slo_separates_public_pages_from_internal_api(self) -> None:
        captured: dict[str, object] = {}

        def collect_stub(**kwargs):
            captured.update(kwargs)
            return http_pass_report()

        with patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            side_effect=collect_stub,
        ):
            check = gate._http_slo_check(
                base_url="http://127.0.0.1:18001",
                page_base_url="https://www.yn-sourcing.com",
                api_prefix="",
                headers={"Authorization": "Bearer token"},
                admin_headers={},
                target_ms=1_000,
                timeout_seconds=30,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.PASS)
        probes = captured["probes"]
        page_probes = [probe for probe in probes if probe.kind == "page"]
        api_probes = [probe for probe in probes if probe.kind == "api"]
        self.assertTrue(page_probes)
        self.assertTrue(api_probes)
        self.assertTrue(
            all(
                probe.path.startswith("https://www.yn-sourcing.com/")
                for probe in page_probes
            )
        )
        self.assertTrue(
            all(probe.path.startswith("/api/") for probe in api_probes)
        )


if __name__ == "__main__":
    unittest.main()
