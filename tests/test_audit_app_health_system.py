from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import unittest

from fin_ops_platform.services.api_performance_metrics import ApiPerformanceRecorder
from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.external_control_evidence import ExternalControlEvidenceService
from fin_ops_platform.services.operations_dashboard import OperationsDashboardService
from fin_ops_platform.services.page_audit_registry import PAGE_AUDIT_REGISTRY
from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.app_health_system_audit import (
    audit_app_health_system_snapshot,
)
from fin_ops_platform.services.postgres_repositories.external_control_evidence import (
    PostgresExternalControlEvidenceRepository,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.runtime_worker_registry import worker_registrations
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.external_evidence_test_support import manifest_payload


def _inventory_payload() -> dict[str, object]:
    return {
        "bank": {
            "total_count": 0,
            "latest_synced_at": None,
            "sources": [
                {
                    "key": "bank_transactions",
                    "label": "银行流水",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                }
            ],
            "status": "available",
        },
        "invoice": {
            "total_count": 0,
            "latest_synced_at": None,
            "sources": [
                {"key": "manual", "label": "手工导入", "count": 0, "latest_synced_at": None, "status": "available"},
                {
                    "key": "input_invoice",
                    "label": "进项发票",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                },
                {
                    "key": "output_invoice",
                    "label": "销项发票",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                },
                {
                    "key": "oa_attachment",
                    "label": "OA 解析",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                    "supplementary_count": 0,
                },
            ],
            "status": "available",
        },
        "oa": {
            "total_count": 0,
            "latest_synced_at": None,
            "sources": [
                {"key": "oa_records", "label": "单据", "count": 0, "latest_synced_at": None, "status": "available"},
                {
                    "key": "oa_records_completed",
                    "label": "已完成 OA",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                },
                {
                    "key": "oa_records_in_progress",
                    "label": "进行中 OA",
                    "count": 0,
                    "latest_synced_at": None,
                    "status": "available",
                },
                {"key": "oa_items", "label": "明细", "count": 0, "latest_synced_at": None, "status": "available"},
            ],
            "status": "available",
        },
        "import_events": [],
    }


def _dashboard_payload() -> dict[str, object]:
    return {
        "generated_at": "2026-07-11T12:00:00+00:00",
        "data_inventory": _inventory_payload(),
        "request_performance": {"endpoints": []},
        "runtime_performance": {
            "outbox": {
                "status": "available",
                "pending_count": 0,
                "publishing_count": 0,
                "failed_count": 0,
                "publish_failed_count": 0,
            },
            "queues": [{"status": "unknown", "warning_code": "rabbitmq_metrics_unavailable"}],
            "read_models": [
                {
                    "key": key,
                    "stale_count": 0,
                    "unavailable_count": 0,
                    "status": "available",
                }
                for key in APP_STATUS_READ_MODEL_REGISTRY
            ],
            "workers": [
                {
                    "worker_instance": registration.instance_name,
                    "worker_kind": registration.worker_kind,
                    "status": "available",
                    "required": True,
                    "current_effective": True,
                }
                for registration in worker_registrations(required_only=True)
            ],
        },
        "freshness": {"warnings": ["rabbitmq_metrics_unavailable"]},
    }


class FakeSystemAuditConnection:
    def __init__(self) -> None:
        self.transaction_count = 0
        self.executed: list[str] = []

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append(" ".join(sql.split()).lower())

    def fetch_one(self, sql: str, params: object = None) -> dict[str, object]:
        normalized = " ".join(sql.split()).lower()
        if "pg_current_snapshot" in normalized:
            return {
                "snapshot_identity": "100:100:",
                "snapshot_generated_at": datetime(2026, 7, 11, 12, 0, tzinfo=UTC),
            }
        if "from app.bank_transactions bank" in normalized:
            return {"total_count": 0, "latest_synced_at": None}
        if "with canonical as" in normalized:
            return {
                "total_count": 0,
                "manual_count": 0,
                "input_invoice_count": 0,
                "output_invoice_count": 0,
                "oa_attachment_count": 0,
                "oa_attachment_non_manual_count": 0,
            }
        if "with pending_ids as" in normalized:
            return {
                "oa_records_count": 0,
                "oa_records_completed_count": 0,
                "oa_records_in_progress_count": 0,
                "oa_items_count": 0,
            }
        raise AssertionError(f"Unexpected fetch_one SQL: {sql}")

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        normalized = " ".join(sql.split()).lower()
        if "from app.import_batches" in normalized:
            return []
        if "from audit.external_control_evidence" in normalized:
            return []
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class StubPageProofRepository(PostgresOperationsAuditRepository):
    def __init__(self, connection: FakeSystemAuditConnection, *, failing_page: str = "") -> None:
        super().__init__(connection)
        self.failing_page = failing_page
        self.snapshots: list[object] = []

    def _audit_registration(self, registration, **kwargs):  # type: ignore[override]
        snapshot = kwargs.get("audit_snapshot")
        self.snapshots.append(snapshot)
        failed = registration.page_key == self.failing_page
        return self._registered_payload(
            {
                "overall_status": "issues_found" if failed else "pass",
                "audit_status": {
                    "integrity": "issues_found" if failed else "pass",
                    "freshness": "fresh",
                    "queue": "drained",
                },
                "summary": {"blocking_issue_sample_count": 1 if failed else 0},
                "issues": ([{"code": "fixture_failure"}] if failed else []),
                "audit_contract": {
                    "database_snapshot": True,
                    "snapshot_consistency": "repeatable_read_read_only",
                },
            },
            registration,
            system_snapshot_identity=str(kwargs.get("system_snapshot_identity") or ""),
        )


class AppHealthSystemAuditTests(unittest.TestCase):
    def test_system_repository_uses_one_outer_snapshot_for_every_page(self) -> None:
        connection = FakeSystemAuditConnection()
        repository = StubPageProofRepository(connection)

        report = repository.audit_system(
            tenant_id="default",
            sample_limit=10,
            dashboard_payload_builder=lambda snapshot_connection: (
                self.assertIs(snapshot_connection, connection) or _dashboard_payload()
            ),
        )

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            connection.executed,
            [
                "set transaction isolation level repeatable read read only",
                "select set_config('statement_timeout', %s, true)",
            ],
        )
        self.assertEqual(len(repository.snapshots), 17)
        self.assertEqual(len({id(snapshot) for snapshot in repository.snapshots}), 1)
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["summary"]["registered_page_count"], 18)
        self.assertEqual(report["summary"]["audited_business_page_count"], 17)
        self.assertEqual(
            set(report["audit_contract"]["audited_business_page_keys"]),
            set(report["audit_contract"]["registered_page_keys"]) - {"app-health-operations"},
        )
        self.assertEqual(report["audit_contract"]["system_page_key"], "app-health-operations")
        self.assertEqual(report["external_evidence"]["status"], "unknown")
        self.assertEqual(report["external_evidence"]["end_to_end_source_truth"], "unproven")
        self.assertTrue(report["database_system_snapshot"]["evidence_fingerprint"])
        self.assertEqual(report["runtime_observation"]["database_snapshot"], False)

    def test_any_child_page_failure_blocks_the_system_internal_proof(self) -> None:
        connection = FakeSystemAuditConnection()
        repository = StubPageProofRepository(connection, failing_page="input-invoice-usage")

        report = repository.audit_system(
            tenant_id="default",
            sample_limit=10,
            dashboard_payload_builder=lambda _connection: _dashboard_payload(),
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertIn(
            "system_page_integrity_failed",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_dashboard_inventory_drift_fails_closed(self) -> None:
        connection = FakeSystemAuditConnection()
        reports = []
        for registration in PAGE_AUDIT_REGISTRY.values():
            if registration.executor == "system":
                continue
            reports.append(
                StubPageProofRepository._registered_payload(
                    {
                        "overall_status": "pass",
                        "audit_status": {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
                        "summary": {},
                        "issues": [],
                        "audit_contract": {
                            "database_snapshot": True,
                            "snapshot_consistency": "repeatable_read_read_only",
                        },
                    },
                    registration,
                    system_snapshot_identity="100:100:",
                )
            )
        dashboard = _dashboard_payload()
        dashboard["data_inventory"]["bank"]["total_count"] = 1  # type: ignore[index]

        report = audit_app_health_system_snapshot(
            connection,
            tenant_id="default",
            sample_limit=10,
            snapshot_identity="100:100:",
            snapshot_generated_at="2026-07-11T12:00:00+00:00",
            snapshot_consistency="repeatable_read_read_only",
            database_snapshot=True,
            registrations=tuple(PAGE_AUDIT_REGISTRY.values()),
            page_reports=reports,
            dashboard_payload=dashboard,
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertIn(
            "app_health_inventory_projection_mismatch",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_current_outbox_and_required_worker_failure_block_system_status(self) -> None:
        connection = FakeSystemAuditConnection()
        repository = StubPageProofRepository(connection)
        dashboard = _dashboard_payload()
        dashboard["runtime_performance"]["outbox"]["pending_count"] = 1  # type: ignore[index]
        dashboard["runtime_performance"]["workers"] = dashboard["runtime_performance"]["workers"][1:]  # type: ignore[index]

        report = repository.audit_system(
            tenant_id="default",
            sample_limit=10,
            dashboard_payload_builder=lambda _connection: dashboard,
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")
        self.assertIn("page_runtime_queue_not_drained", report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("required_worker_missing", report["summary"]["issue_sample_counts_by_code"])

    def test_unknown_outbox_metric_fails_closed_instead_of_treating_null_as_zero(self) -> None:
        connection = FakeSystemAuditConnection()
        repository = StubPageProofRepository(connection)
        dashboard = _dashboard_payload()
        dashboard["runtime_performance"]["outbox"] = {  # type: ignore[index]
            "status": "unknown",
            "warning_code": "outbox_metrics_unavailable",
            "pending_count": None,
            "publishing_count": None,
            "failed_count": None,
            "publish_failed_count": None,
        }

        report = repository.audit_system(
            tenant_id="default",
            sample_limit=10,
            dashboard_payload_builder=lambda _connection: dashboard,
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["queue"], "backlog")
        self.assertIn("page_runtime_queue_not_drained", report["summary"]["issue_sample_counts_by_code"])
        queue_issue = next(issue for issue in report["issues"] if issue["subject_id"] == "system-outbox")
        self.assertEqual(queue_issue["details"]["warning_code"], "outbox_metrics_unavailable")


class AppHealthSystemAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self._seed_clean_system()

    def _seed_clean_system(self) -> None:
        settings = AppSettingsService._normalize_settings({}, validate_pending_invoice_tag_groups=False)
        settings = AppSettingsService._normalize_settings(settings, validate_pending_invoice_tag_groups=False)
        self.connection.execute(
            """
            insert into app.app_settings(settings_key, version, settings_payload, raw_payload)
            values ('app_settings', 1, %s::jsonb, %s::jsonb)
            """,
            (json.dumps(settings), json.dumps({"normalized_payload": settings})),
        )
        for registration in worker_registrations(required_only=True):
            payload = {
                "worker_instance": registration.instance_name,
                "configured_event_types": list(registration.event_types),
            }
            self.connection.execute(
                """
                insert into job.runtime_worker_heartbeats(
                    worker_id, worker_kind, status, payload, raw_payload
                ) values (%s, %s, 'idle', %s::jsonb, %s::jsonb)
                """,
                (
                    registration.instance_name,
                    registration.worker_kind,
                    json.dumps(payload),
                    json.dumps({"normalized_payload": payload}),
                ),
            )
        read_models = PostgresReadModelRepository(self.connection)

        for relation_scope in ("all", "2026-01"):
            read_models.mark_workbench_relation_scope_empty(
                scope_key=relation_scope,
                tenant_id="default",
                source_versions=read_models.workbench_relation_source_summary_from_source(
                    scope_key=relation_scope,
                ),
            )

        PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            relation_command_service_for_transaction=lambda transaction: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(transaction),
                require_fresh_relations=False,
            ),
        ).commit_authoritative_snapshot(
            scope_key="2026-01",
            tenant_id="default",
            projection_records=[],
            admission_records=[],
            payment_statuses={},
        )

    @staticmethod
    def _dashboard(connection: object) -> dict[str, object]:
        return OperationsDashboardService(
            connection,
            api_performance_recorder=ApiPerformanceRecorder(),
        ).build_payload()

    def test_full_migration_clean_and_destructive_fail_closed_proof(self) -> None:
        repository = PostgresOperationsAuditRepository(self.connection)
        clean = repository.audit_system(
            tenant_id="default",
            sample_limit=20,
            dashboard_payload_builder=self._dashboard,
        )
        self.assertEqual(clean["overall_status"], "pass")
        self.assertEqual(
            clean["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained", "external": "unknown"},
        )
        self.assertEqual(clean["summary"]["passed_business_page_count"], 16)
        self.assertTrue(clean["database_system_snapshot"]["snapshot_identity"])

        def drifted_dashboard(connection: object) -> dict[str, object]:
            payload = deepcopy(self._dashboard(connection))
            payload["data_inventory"]["bank"]["total_count"] = 99
            return payload

        inventory_drift = repository.audit_system(
            tenant_id="default",
            sample_limit=20,
            dashboard_payload_builder=drifted_dashboard,
        )
        self.assertIn(
            "app_health_inventory_projection_mismatch",
            inventory_drift["summary"]["issue_sample_counts_by_code"],
        )

        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status, raw_payload
            ) values (
                'system-proof-bank-1', '6222', 'outflow', '系统证明反例',
                100, -100, '2026-07-11', '2026-07-01', 'active', '{}'::jsonb
            )
            """
        )
        direct_canonical_insert = repository.audit_system(
            tenant_id="default",
            sample_limit=20,
            dashboard_payload_builder=self._dashboard,
        )
        self.assertEqual(direct_canonical_insert["overall_status"], "pass")
        self.assertNotIn(
            "system_page_integrity_failed",
            direct_canonical_insert["summary"]["issue_sample_counts_by_code"],
        )

    def test_registered_empty_external_snapshots_bind_system_audit_and_page_coverage(self) -> None:
        now = datetime.now(UTC)
        evidence_service = ExternalControlEvidenceService(PostgresExternalControlEvidenceRepository(self.connection))
        for domain in ("bank", "oa", "invoice", "etc"):
            evidence_service.register(
                manifest_payload(
                    domain,
                    [],
                    observed_at=now,
                    valid_until=now + timedelta(days=1),
                ),
                actor="test-operator",
                reason="empty-source-system-proof",
            )

        report = PostgresOperationsAuditRepository(self.connection).audit_system(
            tenant_id="default",
            sample_limit=20,
            dashboard_payload_builder=self._dashboard,
        )

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["audit_status"]["external"], "pass")
        self.assertEqual(report["summary"]["end_to_end_source_truth"], "proven_as_of_external_evidence")
        self.assertEqual(report["external_evidence"]["summary"]["passed_domain_count"], 4)
        self.assertTrue(
            all(
                item["status"] == "pass"
                for item in report["external_evidence"]["page_coverage"]
                if item["page_key"] not in {"app-health-operations", "operation-history"}
            )
        )


if __name__ == "__main__":
    unittest.main()
