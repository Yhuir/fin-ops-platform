from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

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
            "failed_jobs": 0,
            "rabbitmq_unpublished_backlog": 0,
            "rabbitmq_publishing_backlog": 0,
            "rabbitmq_publish_failed_backlog": 0,
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
        queues["oa.sync.requested"] = {
            "queue": "finops.oa.sync.requested",
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


class RequiredWorkerOverrideMonitoringRepository(FakeRuntimeMonitoringRepository):
    required_worker_instances: set[str] | None = None

    def ready_health_summary(
        self,
        *,
        required_worker_instances: set[str] | None = None,
    ) -> dict[str, object]:
        type(self).required_worker_instances = required_worker_instances
        return super().ready_health_summary()


class CandidateWorkerContractMismatchMonitoringRepository(
    RequiredWorkerOverrideMonitoringRepository
):
    def ready_health_summary(
        self,
        *,
        required_worker_instances: set[str] | None = None,
    ) -> dict[str, object]:
        summary = super().ready_health_summary(
            required_worker_instances=required_worker_instances,
        )
        summary["mismatched_required_worker_count"] = 1
        return summary


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


def http_latency_fail_report() -> dict[str, object]:
    return {
        "status": "fail",
        "auth_configured": True,
        "summary": {"probe_count": 1, "sample_count": 3, "failed_probe_count": 1},
        "probes": [
            {
                "name": "workbench_groups_all_paired",
                "status": "fail",
                "sample_count": 3,
                "success_count": 3,
                "failure_count": 0,
                "slo_pass": False,
                "p95_pass": False,
                "p99_pass": True,
                "errors": [],
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
            object(),
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={},
            tenant_id="default",
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
                object(),
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                tenant_id="default",
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(check.payload["audit_count"], 1)
        self.assertEqual(check.payload["system_audits"], [audit])
        self.assertEqual(check.payload["verification_source"], "current_http_api")
        wait_for_audit.assert_called_once()

    def test_page_canonical_audit_bootstraps_candidate_audit_code_after_valid_http_failure(self) -> None:
        current_audit = {
            "status": "fail",
            "error": "system_audit_registry_contract_failed",
        }
        candidate_audit = {
            "status": "pass",
            "system_audit_id": "system-audit:candidate",
            "snapshot_identity": "snapshot:candidate",
            "external_evidence": "pass",
        }
        with patch.object(
            gate.write_operation_e2e_smoke,
            "_wait_for_system_audit",
            return_value=current_audit,
        ), patch.object(
            gate,
            "_candidate_system_audit",
            return_value=candidate_audit,
        ) as candidate_system_audit:
            check = gate._page_canonical_audit_check(
                object(),
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                tenant_id="default",
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(check.payload["verification_source"], "candidate_read_only_snapshot")
        self.assertEqual(check.payload["current_http_audit"], current_audit)
        self.assertEqual(check.payload["candidate_audit"], candidate_audit)
        self.assertEqual(check.payload["system_audits"], [candidate_audit])
        candidate_system_audit.assert_called_once()

    def test_page_canonical_audit_does_not_bootstrap_transport_or_auth_failure(self) -> None:
        current_audit = {"status": "fail", "error": "unexpected_status:401"}
        with patch.object(
            gate.write_operation_e2e_smoke,
            "_wait_for_system_audit",
            return_value=current_audit,
        ), patch.object(gate, "_candidate_system_audit") as candidate_system_audit:
            check = gate._page_canonical_audit_check(
                object(),
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                tenant_id="default",
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["error"], "unexpected_status:401")
        candidate_system_audit.assert_not_called()

    def test_page_canonical_audit_still_fails_when_candidate_snapshot_fails(self) -> None:
        current_audit = {
            "status": "fail",
            "error": "system_audit_internal_gate_failed",
        }
        candidate_audit = {"status": "fail", "error": "system_audit_business_pages_failed"}
        with patch.object(
            gate.write_operation_e2e_smoke,
            "_wait_for_system_audit",
            return_value=current_audit,
        ), patch.object(
            gate,
            "_candidate_system_audit",
            return_value=candidate_audit,
        ):
            check = gate._page_canonical_audit_check(
                object(),
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                tenant_id="default",
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["error"], "system_audit_business_pages_failed")
        self.assertEqual(check.payload["system_audits"], [])

    def test_candidate_system_audit_preserves_bounded_failure_diagnostics(self) -> None:
        issues = [{"code": f"issue-{index}"} for index in range(12)]
        report = {
            "overall_status": "issues_found",
            "audit_status": {"integrity": "issues_found"},
            "summary": {"blocking_issue_sample_count": 12},
            "issues": issues,
            "database_system_snapshot": {
                "page_results": [
                    {
                        "page_key": "imports.bank-transactions",
                        "overall_status": "issues_found",
                        "audit_status": {"integrity": "issues_found"},
                        "summary": {"blocking_issue_sample_count": 12},
                        "issues": issues,
                    },
                    {
                        "page_key": "imports.invoices",
                        "overall_status": "pass",
                        "issues": [],
                    },
                ]
            },
        }
        with patch.object(
            gate.PostgresOperationsAuditRepository,
            "audit_system",
            return_value=report,
        ), patch.object(
            gate.write_operation_e2e_smoke,
            "_collect_system_audit",
            return_value={
                "status": "fail",
                "error": "system_audit_page_count_or_contract_failed",
            },
        ):
            result = gate._candidate_system_audit(
                object(),
                tenant_id="default",
                timeout_seconds=1,
            )

        self.assertEqual(result["status"], gate.FAIL)
        self.assertEqual(result["diagnostics"]["overall_status"], "issues_found")
        self.assertEqual(
            result["diagnostics"]["summary"],
            {"blocking_issue_sample_count": 12},
        )
        self.assertEqual(result["diagnostics"]["issues"], issues[:10])
        self.assertEqual(
            result["diagnostics"]["failed_page_reports"],
            [
                {
                    "page_key": "imports.bank-transactions",
                    "overall_status": "issues_found",
                    "audit_status": {"integrity": "issues_found"},
                    "summary": {"blocking_issue_sample_count": 12},
                    "issues": issues[:10],
                }
            ],
        )


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

    def test_missing_rabbitmq_management_metrics_prevents_runtime_closure(self) -> None:
        blockers = gate._runtime_blockers(
            {
                "queue_backlog": {},
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
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
        ) as http_slo, patch.object(
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
        http_slo.assert_not_called()
        business_write_e2e.assert_not_called()

    def test_preflight_allows_compatible_previous_page_registry(self) -> None:
        page_audit = Mock(
            return_value=gate.ClosureCheck(
                "page_canonical_audit",
                gate.PASS,
                "pass",
                {"status": "pass", "audit_count": 1},
            )
        )
        with patch.object(gate, "_page_canonical_audit_check", page_audit):
            gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                profile="preflight",
            )
            preflight_call = page_audit.call_args

        self.assertTrue(preflight_call.kwargs["allow_compatible_previous_registry"])

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

    def test_runtime_health_can_use_stable_release_worker_inventory(self) -> None:
        RequiredWorkerOverrideMonitoringRepository.required_worker_instances = None
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            RequiredWorkerOverrideMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                object(),
                timeout_seconds=0,
                poll_interval_seconds=0.05,
                required_worker_instances={"import", "oa-sync"},
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(
            RequiredWorkerOverrideMonitoringRepository.required_worker_instances,
            {"import", "oa-sync"},
        )

    def test_preflight_allows_active_worker_contract_until_candidate_cutover(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            CandidateWorkerContractMismatchMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                object(),
                timeout_seconds=0,
                poll_interval_seconds=0.05,
                required_worker_instances={"settings-maintenance"},
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(
            check.payload["required_worker_contract"],
            "active_release_compatible",
        )
        self.assertEqual(
            check.payload["snapshot"]["mismatched_required_worker_count"],
            1,
        )

    def test_post_cutover_keeps_candidate_worker_contract_strict(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            CandidateWorkerContractMismatchMonitoringRepository,
        ):
            check = gate._runtime_health_check(
                object(),
                timeout_seconds=0,
                poll_interval_seconds=0.05,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(
            check.payload["blockers"]["mismatched_required_worker_count"],
            1,
        )
        self.assertEqual(
            check.payload["required_worker_contract"],
            "strict_current_release",
        )

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
            queue["oa.sync.requested"]["messages"],
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
            gate.http_slo_probe,
            "collect_http_slo",
            return_value=http_pass_report(),
        ), patch.object(
            gate.write_operation_e2e_smoke,
            "run_write_operation_e2e_smoke",
        ) as business_write_e2e:
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(
            [check["name"] for check in report["checks"]],
            [
                "postgres_reversible_write",
                "authenticated_http_slo",
                "health_ready_payload",
                "runtime_health_before_final_convergence",
                "runtime_health",
                "page_canonical_audit",
            ],
        )
        business_write_e2e.assert_not_called()

    def test_stability_gate_is_read_only(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value=http_pass_report(),
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
                profile="stability",
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertIn("page_canonical_audit", [check["name"] for check in report["checks"]])

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
            gate.http_slo_probe,
            "collect_http_slo",
            return_value={
                "status": "auth_missing",
                "auth_configured": False,
                "summary": {"probe_count": 0, "sample_count": 0},
            },
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={},
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("page_canonical_audit", report["failed_checks"])
        self.assertIn("authenticated_http_slo", report["failed_checks"])
        self.assertFalse(report["auth_configured"])

    def test_gate_passes_admin_headers_to_http_and_canonical_audit(self) -> None:
        captured_http: dict[str, object] = {}
        captured_audit: dict[str, object] = {}

        def collect_http(**kwargs):
            captured_http.update(kwargs)
            return http_pass_report()

        def collect_audit(*_args, **kwargs):
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
            gate.http_slo_probe,
            "collect_http_slo",
            side_effect=collect_http,
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer user"},
                admin_headers={"Cookie": "Admin-Token=admin"},
            )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(captured_http["admin_headers"], {"Cookie": "Admin-Token=admin"})
        self.assertEqual(captured_audit["headers"], {"Cookie": "Admin-Token=admin"})

    def test_empty_http_probe_samples_fail_closed(self) -> None:
        with patch.object(
            gate,
            "RuntimeMonitoringRepository",
            FakeRuntimeMonitoringRepository,
        ), patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            return_value={
                "status": "pass",
                "summary": {"probe_count": 0, "sample_count": 0},
                "probes": [],
            },
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("authenticated_http_slo", report["failed_checks"])

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
        self.assertTrue(all(probe.target_ms == 1_000 for probe in probes))
        self.assertTrue(
            all(
                probe.p99_target_ms == gate.http_slo_probe.DEFAULT_P99_TARGET_MS
                for probe in probes
            )
        )
        self.assertTrue(
            all(
                probe.path.startswith("https://www.yn-sourcing.com/")
                for probe in page_probes
            )
        )
        self.assertTrue(
            all(probe.path.startswith("/api/") for probe in api_probes)
        )

    def test_http_slo_retries_one_clean_latency_window(self) -> None:
        with patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            side_effect=[http_latency_fail_report(), http_pass_report()],
        ) as collect, patch.object(
            gate,
            "monotonic",
            side_effect=[0.0, 0.1, 0.2],
        ), patch.object(gate, "sleep") as sleep:
            check = gate._http_slo_check(
                base_url="https://example.test",
                page_base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                admin_headers={},
                target_ms=1_000,
                timeout_seconds=1,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.PASS)
        self.assertEqual(check.payload["retry_attempts"], 1)
        self.assertEqual(collect.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_http_slo_fails_after_two_latency_windows(self) -> None:
        with patch.object(
            gate.http_slo_probe,
            "collect_http_slo",
            side_effect=[http_latency_fail_report(), http_latency_fail_report()],
        ) as collect, patch.object(
            gate,
            "monotonic",
            side_effect=[0.0, 0.1, 0.2],
        ), patch.object(gate, "sleep") as sleep:
            check = gate._http_slo_check(
                base_url="https://example.test",
                page_base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                admin_headers={},
                target_ms=1_000,
                timeout_seconds=1,
                require_auth=True,
            )

        self.assertEqual(check.status, gate.FAIL)
        self.assertEqual(check.payload["retry_attempts"], 1)
        self.assertEqual(collect.call_count, 2)
        sleep.assert_called_once_with(0.5)


if __name__ == "__main__":
    unittest.main()
