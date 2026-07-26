from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import unittest

from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.services.app_status_domain_registry import (
    APP_STATUS_DOMAIN_REGISTRY,
    domain_routes,
)
from fin_ops_platform.services.app_status_dependency_registry import APP_STATUS_DEPENDENCY_REGISTRY
from fin_ops_platform.services.app_status_job_registry import APP_STATUS_BACKGROUND_JOB_REGISTRY
from fin_ops_platform.services.app_status_overview_service import AppStatusOverviewService
from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.background_job_service import BackgroundJob, BackgroundJobService
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
from fin_ops_platform.services.runtime_state_policy import BACKGROUND_JOB_KNOWN_TYPES
from fin_ops_platform.services.runtime_worker_registry import registration_by_instance_name


FRONTEND_ROUTES = {
    "/",
    "/imports/bank-transactions",
    "/imports/invoices",
    "/imports/etc-invoices",
    "/tax-offset",
    "/cost-statistics",
    "/bank-details",
    "/pending-invoices",
    "/input-invoice-usage",
    "/oa-pending-payments",
    "/output-invoice-collections",
    "/bank-flow-rule-batches",
    "/batch-accounting",
    "/turnover-ledger",
    "/etc-tickets",
    "/settings",
    "/operations/app-health",
}


@dataclass(slots=True)
class FakeIdentity:
    user_id: str = "u1"
    username: str = "tester"
    display_name: str = "测试用户"


@dataclass(slots=True)
class FakeSession:
    identity: FakeIdentity
    allowed: bool = True
    access_tier: str = "admin"
    can_access_app: bool = True
    can_mutate_data: bool = True
    can_admin_access: bool = True


@dataclass(slots=True)
class FakeJob:
    job_id: str
    type: str
    status: str
    label: str = "后台任务"
    short_label: str = "后台任务处理中"
    message: str = "后台任务处理中。"
    phase: str = "running"
    current: int = 0
    total: int = 0
    percent: int = 0
    updated_at: str = "2026-06-04T10:00:00+00:00"
    affected_scopes: list[str] | None = None
    affected_months: list[str] | None = None
    error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "label": self.label,
            "short_label": self.short_label,
            "message": self.message,
            "phase": self.phase,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "updated_at": self.updated_at,
            "affected_scopes": self.affected_scopes or [],
            "affected_months": self.affected_months or [],
            "error": self.error,
        }


def healthy_dependencies() -> dict[str, dict[str, str]]:
    return {
        key: {"status": "available", "message": ""}
        for key in APP_STATUS_DEPENDENCY_REGISTRY
    }


class AppStatusOverviewServiceTests(unittest.TestCase):
    def test_domain_registry_covers_frontend_routes(self) -> None:
        self.assertEqual(set(domain_routes(APP_STATUS_DOMAIN_REGISTRY)), FRONTEND_ROUTES)

    def test_domain_registry_has_runtime_fact_sources_for_every_mapping(self) -> None:
        read_model_keys = set(APP_STATUS_READ_MODEL_REGISTRY)
        worker_instances = set(registration_by_instance_name())
        job_types = set(APP_STATUS_BACKGROUND_JOB_REGISTRY) | set(BACKGROUND_JOB_KNOWN_TYPES)
        dependency_keys = set(APP_STATUS_DEPENDENCY_REGISTRY)

        missing_read_models: dict[str, list[str]] = {}
        missing_workers: dict[str, list[str]] = {}
        missing_job_types: dict[str, list[str]] = {}
        missing_dependencies: dict[str, list[str]] = {}
        for domain in APP_STATUS_DOMAIN_REGISTRY:
            missing_read_models[domain.key] = [key for key in domain.read_model_keys if key not in read_model_keys]
            missing_workers[domain.key] = [key for key in domain.worker_instances if key not in worker_instances]
            missing_job_types[domain.key] = [key for key in domain.job_types if key not in job_types]
            missing_dependencies[domain.key] = [key for key in domain.dependencies if key not in dependency_keys]

        self.assertFalse({key: value for key, value in missing_read_models.items() if value})
        self.assertFalse({key: value for key, value in missing_workers.items() if value})
        self.assertFalse({key: value for key, value in missing_job_types.items() if value})
        self.assertFalse({key: value for key, value in missing_dependencies.items() if value})

    def test_running_background_task_marks_overall_yellow_and_projects_task_progress(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)
        job = FakeJob(
            job_id="job_etc_001",
            type="etc_invoice_import",
            status="running",
            label="导入 ETC发票",
            short_label="正在导入 ETC发票 3/31",
            message="正在导入 ETC发票。",
            current=3,
            total=31,
            percent=10,
            affected_months=["2026-05"],
        )

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[job],
            attention_jobs=[],
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertEqual(payload["overall"]["color"], "yellow")
        self.assertEqual(payload["overall"]["level"], "busy")
        self.assertEqual(payload["background_tasks"][0]["job_id"], "job_etc_001")
        self.assertEqual(payload["background_tasks"][0]["percent"], 10)
        self.assertIn("imports_etc_invoices", payload["background_tasks"][0]["affected_domains"])

    def test_failed_critical_read_model_marks_domain_and_overall_red_without_blocking_writes(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            read_model_statuses={
                "bank_detail": {"status": "failed", "last_error": "projection failed"},
            },
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "blocked",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertEqual(payload["overall"]["color"], "red")
        self.assertEqual(payload["overall"]["level"], "blocked")
        self.assertFalse(payload["overall"]["blocks_mutations"])
        self.assertEqual(payload["overall"]["write_safety"]["status"], "ready")
        self.assertEqual(payload["overall"]["write_safety"]["blockers"], [])
        bank_domain = next(domain for domain in payload["domains"] if domain["key"] == "bank_details")
        self.assertEqual(bank_domain["status"], "failed")
        self.assertEqual(bank_domain["level"], "blocked")
        self.assertIn("projection failed", bank_domain["details"])

    def test_missing_readiness_record_keeps_domain_busy_and_overall_yellow(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            read_model_statuses={
                "bank_detail": {"status": "missing", "reason": "readiness record missing"},
            },
            worker_statuses={"bank-detail": {"status": "ready"}},
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        bank_domain = next(domain for domain in payload["domains"] if domain["key"] == "bank_details")
        self.assertEqual(bank_domain["level"], "busy")
        self.assertEqual(bank_domain["status"], "missing")
        self.assertEqual(payload["overall"]["color"], "yellow")

    def test_runtime_summary_counts_read_models_workers_and_queue_backlog(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            read_model_statuses={
                "bank_detail": {"status": "fresh"},
                "search": {
                    "status": "refreshing",
                    "scopes": [
                        {
                            "read_model_key": "search",
                            "scope_type": "search",
                            "scope_key": "all",
                            "status": "fresh",
                        },
                        {
                            "read_model_key": "search",
                            "scope_type": "search",
                            "scope_key": "2026-05",
                            "status": "failed",
                            "last_error": "projection failed",
                        },
                    ],
                },
                "pending_invoice": {"status": "failed", "last_error": "projection failed"},
                "turnover_ledger": {"status": "missing"},
            },
            worker_statuses={
                "runtime-worker": {"status": "ready", "required": True},
                "cost-tax": {"status": "working", "required": True},
                "bank-detail": {"status": "stale", "required": True, "warning_code": "heartbeat_stale"},
                "legacy-worker": {"status": "missing", "required": False, "warning_code": "required_worker_missing"},
            },
            outbox_statuses={
                "bank_detail.read_model.refresh": {"status": "pending", "count": 2},
                "search.read_model.refresh": {"status": "processing", "count": 1},
                "pending_invoice.read_model.refresh": {"status": "failed", "count": 3},
            },
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertEqual(
            payload["runtime_summary"]["read_models"],
            {
                "total": 4,
                "fresh": 1,
                "refreshing": 1,
                "stale": 0,
                "missing": 1,
                "failed": 1,
                "unavailable": 0,
                "issue_count": 3,
                "scope_issue_count": 1,
            },
        )
        self.assertEqual(payload["runtime_summary"]["workers"]["total"], 4)
        self.assertEqual(payload["runtime_summary"]["workers"]["required"], 3)
        self.assertEqual(payload["runtime_summary"]["workers"]["ready"], 1)
        self.assertEqual(payload["runtime_summary"]["workers"]["working"], 1)
        self.assertEqual(payload["runtime_summary"]["workers"]["stale"], 1)
        self.assertEqual(payload["runtime_summary"]["workers"]["missing"], 1)
        self.assertEqual(payload["runtime_summary"]["workers"]["issue_count"], 2)
        self.assertEqual(
            payload["runtime_summary"]["queue"],
            {
                "event_type_count": 3,
                "pending": 2,
                "processing": 1,
                "failed": 3,
                "backlog": 6,
            },
        )

    def test_oa_sync_outbox_marks_oa_pending_without_marking_settings_busy(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            read_model_statuses={
                "oa_pending_payment": {"status": "fresh"},
                "invoice_lifecycle": {"status": "fresh"},
            },
            worker_statuses={
                "oa-sync": {"status": "ready", "required": True},
            },
            outbox_statuses={
                "oa.sync": {"status": "pending", "count": 1},
            },
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        domain_levels = {domain["key"]: domain["level"] for domain in payload["domains"]}
        self.assertEqual(domain_levels["oa_pending_payments"], "busy")
        self.assertEqual(domain_levels["settings"], "ok")

    def test_missing_critical_dependency_key_is_blocked_not_available(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)
        dependencies = healthy_dependencies()
        dependencies.pop("state_store")

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "blocked",
                "dependencies": dependencies,
                "alerts": {"active": []},
            },
        )

        self.assertEqual(payload["overall"]["level"], "blocked")
        self.assertEqual(payload["overall"]["color"], "red")
        self.assertIn("state_store", payload["overall"]["reason"])
        self.assertTrue(payload["overall"]["blocks_mutations"])
        self.assertEqual(payload["overall"]["write_safety"]["status"], "blocked")
        self.assertEqual(payload["overall"]["write_safety"]["blockers"], ["dependency"])


class FakeRuntimeConnection:
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            return [
                {
                    "event_type": "bank_detail.read_model.refresh",
                    "scope_type": "bank_detail",
                    "scope_key": "2026-03",
                    "status": "pending",
                    "count": 1,
                    "last_error": None,
                    "updated_at": "2026-06-04T10:00:00+00:00",
                }
            ]
        if "from job.read_model_dirty_scopes" in normalized:
            return [
                {
                    "scope_type": "bank_detail",
                    "status": "processing",
                    "count": 2,
                    "last_error": None,
                    "updated_at": "2026-06-04T10:00:00+00:00",
                }
            ]
        if "from read_model.app_status_readiness" in normalized:
            return [
                {
                    "read_model_key": "bank_detail",
                    "scope_type": "bank_detail",
                    "scope_key": "all",
                    "status": "fresh",
                    "schema_version": "v1",
                    "source_versions": {"bank_transactions": 1},
                    "row_count": 10,
                    "generated_at": "2026-06-04T10:00:00+00:00",
                    "updated_at": "2026-06-04T10:00:00+00:00",
                    "last_error": None,
                }
            ]
        if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
            return [
                {
                    "worker_id": "bank-detail",
                    "worker_instance": "bank-detail",
                    "worker_kind": "bank-detail-read-model",
                    "status": "running",
                    "heartbeat_lag_seconds": 12,
                    "payload": {
                        "worker_instance": "bank-detail",
                        "configured_event_types": ["bank_detail.read_model.refresh"],
                    },
                }
            ]
        raise AssertionError(sql)


class AppStatusRuntimeRepositoryTests(unittest.TestCase):
    def test_runtime_repository_groups_dirty_scopes_outbox_and_workers_for_overview(self) -> None:
        snapshot = RuntimeMonitoringRepository(FakeRuntimeConnection()).app_status_runtime_snapshot()

        self.assertEqual(snapshot["read_model_statuses"]["bank_detail"]["status"], "refreshing")
        self.assertEqual(snapshot["outbox_statuses"]["bank_detail.read_model.refresh"]["status"], "pending")
        self.assertEqual(
            snapshot["outbox_statuses"]["bank_detail.read_model.refresh"]["scopes"],
            [
                {
                    "event_type": "bank_detail.read_model.refresh",
                    "scope_type": "bank_detail",
                    "scope_key": "2026-03",
                    "status": "pending",
                    "count": 1,
                    "updated_at": "2026-06-04T10:00:00+00:00",
                }
            ],
        )
        self.assertEqual(snapshot["worker_statuses"]["bank-detail"]["status"], "ready")

    def test_runtime_repository_reports_registry_read_model_without_readiness_as_missing(self) -> None:
        class NoReadinessConnection(FakeRuntimeConnection):
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    return []
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from read_model.app_status_readiness" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        snapshot = RuntimeMonitoringRepository(NoReadinessConnection()).app_status_runtime_snapshot()

        self.assertEqual(snapshot["read_model_statuses"]["bank_detail"]["status"], "missing")
        self.assertEqual(snapshot["read_model_statuses"]["bank_detail"]["reason"], "readiness record missing")

    def test_runtime_repository_ignores_outbox_rows_covered_by_later_success(self) -> None:
        class CoveredOutboxConnection(FakeRuntimeConnection):
            def __init__(self) -> None:
                self.outbox_sql = ""

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    self.outbox_sql = normalized
                    return [
                        {
                            "event_type": "output_invoice_collection.read_model.refresh",
                            "scope_type": "output_invoice_collection",
                            "scope_key": "2026-05",
                            "status": "dead_lettered",
                            "count": 1,
                            "updated_at": "2026-06-04T09:00:00+00:00",
                            "covered_by_later_done": False,
                            "covered_by_later_readiness": True,
                        },
                        {
                            "event_type": "bank_detail.read_model.refresh",
                            "scope_type": "bank_detail",
                            "scope_key": "all",
                            "status": "failed",
                            "count": 1,
                            "updated_at": "2026-06-04T10:00:00+00:00",
                            "covered_by_later_done": False,
                        },
                        {
                            "event_type": "pending_invoice.read_model.refresh",
                            "scope_type": "pending_invoice",
                            "scope_key": "all",
                            "status": "pending",
                            "count": 1,
                            "updated_at": "2026-06-04T10:01:00+00:00",
                            "covered_by_later_done": True,
                            "covered_by_later_readiness": False,
                        },
                    ]
                if "from read_model.app_status_readiness" in normalized:
                    return []
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        connection = CoveredOutboxConnection()
        snapshot = RuntimeMonitoringRepository(connection).app_status_runtime_snapshot()

        self.assertNotIn("output_invoice_collection.read_model.refresh", snapshot["outbox_statuses"])
        self.assertEqual(snapshot["outbox_statuses"]["bank_detail.read_model.refresh"]["status"], "failed")
        self.assertNotIn("pending_invoice.read_model.refresh", snapshot["outbox_statuses"])
        self.assertIn("e.status <> 'done' and e.publish_status in ('publishing', 'failed')", connection.outbox_sql)
        self.assertIn("when e.publish_status = 'failed' then 'publish_failed'", connection.outbox_sql)
        self.assertIn("done.status = 'done'", connection.outbox_sql)
        self.assertIn("readiness.status = 'fresh'", connection.outbox_sql)

    def test_runtime_repository_does_not_cover_command_parent_dirty_scope_with_historical_readiness(self) -> None:
        class CoveredDirtyScopeConnection(FakeRuntimeConnection):
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.read_model_dirty_scopes" in normalized:
                    return [
                        {
                            "scope_type": "input_invoice_usage",
                            "scope_key": "all",
                            "status": "pending",
                            "count": 1,
                            "last_error": None,
                            "updated_at": "2026-06-04T09:59:00+00:00",
                            "covered_by_later_readiness": True,
                        }
                    ]
                if "from read_model.app_status_readiness" in normalized:
                    return [
                        {
                            "read_model_key": "input_invoice_usage",
                            "scope_type": "input_invoice_usage",
                            "scope_key": "all",
                            "status": "fresh",
                            "schema_version": "v1",
                            "source_versions": {"input_invoices": 7},
                            "row_count": 128,
                            "generated_at": "2026-06-04T10:00:00+00:00",
                            "updated_at": "2026-06-04T10:00:00+00:00",
                            "last_error": None,
                        }
                    ]
                if "from job.outbox_events" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        snapshot = RuntimeMonitoringRepository(CoveredDirtyScopeConnection()).app_status_runtime_snapshot()

        input_usage_status = snapshot["read_model_statuses"]["input_invoice_usage"]
        self.assertEqual(input_usage_status["status"], "refreshing")
        self.assertEqual(input_usage_status["scopes"][0]["status"], "refreshing")
        self.assertEqual(input_usage_status["historical_scopes"][0]["scope_key"], "all")
        self.assertEqual(input_usage_status["historical_scopes"][0]["history_reason"], "fan_out_command_scope")

    def test_runtime_repository_keeps_failed_fan_out_parent_readiness_as_history(self) -> None:
        class FanOutHistoryConnection(FakeRuntimeConnection):
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized or "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from read_model.app_status_readiness" in normalized:
                    return [
                        {
                            "read_model_key": "oa_pending_payment",
                            "scope_type": "oa_pending_payment",
                            "scope_key": "all",
                            "status": "failed",
                            "updated_at": "2026-07-10T20:31:00+08:00",
                            "last_error": "permission denied for table oa_pending_payment_admissions",
                        },
                        {
                            "read_model_key": "oa_pending_payment",
                            "scope_type": "oa_pending_payment",
                            "scope_key": "2026-06",
                            "status": "fresh",
                            "updated_at": "2026-07-10T20:32:00+08:00",
                            "last_error": None,
                        },
                    ]
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        snapshot = RuntimeMonitoringRepository(FanOutHistoryConnection()).app_status_runtime_snapshot()

        status = snapshot["read_model_statuses"]["oa_pending_payment"]
        self.assertEqual(status["status"], "fresh")
        self.assertEqual([scope["scope_key"] for scope in status["scopes"]], ["2026-06"])
        self.assertEqual(status["historical_scopes"][0]["scope_key"], "all")
        self.assertEqual(status["historical_scopes"][0]["current_effective"], False)
        self.assertEqual(status["historical_scopes"][0]["history_reason"], "fan_out_command_scope")

    def test_runtime_repository_keeps_queryable_all_scope_readiness_current(self) -> None:
        class QueryableAllConnection(FakeRuntimeConnection):
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized or "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from read_model.app_status_readiness" in normalized:
                    return [
                        {
                            "read_model_key": "bank_account_balance",
                            "scope_type": "bank_account_balance",
                            "scope_key": "all",
                            "status": "failed",
                            "updated_at": "2026-07-10T20:31:00+08:00",
                            "last_error": "projection failed",
                        }
                    ]
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        snapshot = RuntimeMonitoringRepository(QueryableAllConnection()).app_status_runtime_snapshot()

        status = snapshot["read_model_statuses"]["bank_account_balance"]
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["scopes"][0]["scope_key"], "all")

    def test_runtime_repository_ignores_failed_outbox_row_covered_by_later_pending_retry(self) -> None:
        class CoveredByRetryConnection(FakeRuntimeConnection):
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    return [
                        {
                            "event_type": "oa.sync",
                            "scope_type": "oa",
                            "scope_key": "all",
                            "status": "failed",
                            "count": 1,
                            "updated_at": "2026-06-04T09:59:00+00:00",
                            "covered_by_later_event": True,
                            "covered_by_later_done": False,
                            "covered_by_later_readiness": False,
                        },
                        {
                            "event_type": "oa.sync",
                            "scope_type": "oa",
                            "scope_key": "all",
                            "status": "pending",
                            "count": 1,
                            "updated_at": "2026-06-04T10:00:00+00:00",
                            "covered_by_later_event": False,
                            "covered_by_later_done": False,
                            "covered_by_later_readiness": False,
                        },
                    ]
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from read_model.app_status_readiness" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        snapshot = RuntimeMonitoringRepository(CoveredByRetryConnection()).app_status_runtime_snapshot()

        self.assertEqual(snapshot["outbox_statuses"]["oa.sync"]["status"], "pending")
        self.assertEqual(snapshot["outbox_statuses"]["oa.sync"]["count"], 1)

    def test_runtime_repository_ignores_failed_outbox_row_covered_by_active_dirty_scope(self) -> None:
        class CoveredByDirtyScopeConnection(FakeRuntimeConnection):
            def __init__(self) -> None:
                self.outbox_sql = ""

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    self.outbox_sql = normalized
                    return [
                        {
                            "event_type": "workbench.read_model.refresh",
                            "scope_type": "workbench",
                            "scope_key": "all",
                            "status": "failed",
                            "count": 1,
                            "last_error": "generation_metadata_actual_mismatch",
                            "updated_at": "2026-06-21T22:47:00+08:00",
                            "covered_by_later_event": False,
                            "covered_by_later_done": False,
                            "covered_by_later_readiness": False,
                            "covered_by_active_dirty_scope": True,
                        },
                        {
                            "event_type": "workbench.read_model.refresh",
                            "scope_type": "workbench",
                            "scope_key": "all",
                            "status": "pending",
                            "count": 1,
                            "last_error": None,
                            "updated_at": "2026-06-21T22:48:00+08:00",
                            "covered_by_later_event": False,
                            "covered_by_later_done": False,
                            "covered_by_later_readiness": False,
                            "covered_by_active_dirty_scope": False,
                        },
                    ]
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from read_model.app_status_readiness" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized and "coalesce(payload->>'worker_instance'" in normalized:
                    return []
                raise AssertionError(sql)

        connection = CoveredByDirtyScopeConnection()
        snapshot = RuntimeMonitoringRepository(connection).app_status_runtime_snapshot()

        self.assertEqual(snapshot["outbox_statuses"]["workbench.read_model.refresh"]["status"], "pending")
        self.assertEqual(snapshot["outbox_statuses"]["workbench.read_model.refresh"]["count"], 1)
        self.assertNotIn("last_error", snapshot["outbox_statuses"]["workbench.read_model.refresh"])
        self.assertIn("from job.read_model_dirty_scopes dirty", connection.outbox_sql)
        self.assertIn("covered_by_active_dirty_scope", connection.outbox_sql)
        self.assertIn("e.status in ('failed', 'dead_lettered')", connection.outbox_sql)

    def test_runtime_repository_records_read_model_readiness_through_repository_boundary(self) -> None:
        class RecordingConnection(FakeRuntimeConnection):
            def __init__(self) -> None:
                self.executed: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()):
                self.executed.append((sql, params))

        connection = RecordingConnection()
        RuntimeMonitoringRepository(connection).record_read_model_readiness(
            read_model_key="bank_detail",
            scope_type="bank_detail",
            scope_key="all",
            status="fresh",
            schema_version="v1",
            source_versions={"bank_transactions": 7},
            row_count=12,
            generated_at="2026-06-04T10:00:00+00:00",
        )

        self.assertEqual(len(connection.executed), 1)
        sql, params = connection.executed[0]
        self.assertIn("read_model.app_status_readiness", sql)
        self.assertEqual(params[1:5], ("bank_detail", "bank_detail", "all", "fresh"))
        self.assertIn('"bank_transactions": 7', str(params[6]))

    def test_runtime_repository_rejects_unknown_readiness_status(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeMonitoringRepository(FakeRuntimeConnection()).record_read_model_readiness(
                read_model_key="bank_detail",
                scope_type="bank_detail",
                scope_key="all",
                status="almost_ready",
            )

    def test_runtime_repository_reports_unavailable_snapshot_instead_of_empty_green(self) -> None:
        class BrokenConnection:
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                raise RuntimeError("postgres unavailable")

        snapshot = RuntimeMonitoringRepository(BrokenConnection()).app_status_runtime_snapshot()

        self.assertEqual(snapshot["read_model_statuses"]["__runtime__"]["status"], "unavailable")
        self.assertIn("postgres unavailable", snapshot["read_model_statuses"]["__runtime__"]["last_error"])

    def test_service_marks_runtime_unavailable_as_blocked_not_green(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            read_model_statuses={
                "__runtime__": {"status": "unavailable", "last_error": "postgres unavailable"},
            },
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "blocked",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertEqual(payload["overall"]["color"], "red")
        self.assertEqual(payload["overall"]["level"], "blocked")
        self.assertIn("postgres unavailable", payload["overall"]["reason"])
        self.assertTrue(payload["overall"]["blocks_mutations"])
        self.assertEqual(payload["overall"]["write_safety"]["status"], "blocked")
        self.assertEqual(payload["overall"]["write_safety"]["blockers"], ["runtime"])

    def test_required_worker_missing_marks_critical_domain_blocked(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            attention_jobs=[],
            worker_statuses={
                "bank-detail": {"status": "missing", "warning_code": "required_worker_missing"},
            },
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "blocked",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        bank_domain = next(domain for domain in payload["domains"] if domain["key"] == "bank_details")
        self.assertEqual(bank_domain["level"], "blocked")
        self.assertEqual(payload["overall"]["color"], "red")

    def test_file_import_can_use_explicit_affected_domain_without_marking_all_import_pages(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)
        job = {
            "job_id": "job_import_001",
            "type": "file_import",
            "status": "running",
            "label": "导入发票",
            "short_label": "导入发票",
            "affected_domains": ["imports_invoices"],
        }

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[job],
            attention_jobs=[],
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        task = payload["background_tasks"][0]
        self.assertEqual(task["affected_domains"], ["imports_invoices"])
        busy_domains = {domain["key"] for domain in payload["domains"] if domain["level"] == "busy"}
        self.assertEqual(busy_domains, {"imports_invoices"})

    def test_generic_import_job_defaults_cover_all_import_domains_without_wrong_invoice_route(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)
        job = {
            "job_id": "job_import_001",
            "type": "import.process.requested",
            "status": "running",
            "label": "导入处理",
            "short_label": "导入处理",
        }

        payload = service.build_overview(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[job],
            attention_jobs=[],
            app_health_snapshot={
                "generated_at": "2026-06-04T10:00:00+00:00",
                "status": "busy",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        task = payload["background_tasks"][0]
        self.assertEqual(
            task["affected_domains"],
            ["imports_bank_transactions", "imports_invoices", "imports_etc_invoices"],
        )
        self.assertEqual(task["route"], "/imports/bank-transactions")
        busy_domains = {domain["key"] for domain in payload["domains"] if domain["level"] == "busy"}
        self.assertEqual(busy_domains, {"imports_bank_transactions", "imports_invoices", "imports_etc_invoices"})

    def test_background_job_registry_file_import_default_does_not_point_bank_import_to_invoice_page(self) -> None:
        now = "2026-06-04T10:00:00+00:00"
        payload = BackgroundJob(
            job_id="job_001",
            type="file_import",
            label="导入文件",
            short_label="导入文件",
            owner_user_id="u1",
            visibility="owner",
            status="running",
            phase="persist",
            current=0,
            total=0,
            percent=None,
            message="正在导入文件。",
            result_summary={},
            error=None,
            idempotency_key=None,
            source={},
            affected_scopes=["imports"],
            affected_months=[],
            created_at=now,
            started_at=now,
            updated_at=now,
            finished_at=None,
            acknowledged_at=None,
            superseded_by_job_id=None,
            superseded_at=None,
        ).to_payload()

        self.assertEqual(
            payload["affected_domains"],
            ["imports_bank_transactions", "imports_invoices", "imports_etc_invoices"],
        )
        self.assertEqual(payload["route"], "/operations/app-health")

    def test_background_job_payload_contract_exposes_progress_fields(self) -> None:
        now = "2026-06-04T10:00:00+00:00"
        payload = BackgroundJob(
            job_id="job_001",
            type="file_import",
            label="导入文件",
            short_label="导入文件",
            owner_user_id="u1",
            visibility="owner",
            status="running",
            phase="persist",
            current=0,
            total=0,
            percent=None,
            message="正在导入文件。",
            result_summary={},
            error=None,
            idempotency_key=None,
            source={"affected_domains": ["imports_invoices"]},
            affected_scopes=["2026-05"],
            affected_months=["2026-05"],
            created_at=now,
            started_at=now,
            updated_at=now,
            finished_at=None,
            acknowledged_at=None,
            superseded_by_job_id=None,
            superseded_at=None,
        ).to_payload()

        expected_fields = {
            "job_id",
            "type",
            "status",
            "label",
            "short_label",
            "message",
            "phase",
            "current",
            "total",
            "percent",
            "affected_domains",
            "affected_scopes",
            "affected_months",
            "route",
            "updated_at",
        }
        self.assertFalse(expected_fields - set(payload))
        self.assertIsNone(payload["percent"])

    def test_background_job_payload_preserves_legacy_top_level_domain_and_route(self) -> None:
        job = BackgroundJobService._job_from_payload(
            {
                "job_id": "job_legacy",
                "type": "file_import",
                "label": "导入文件",
                "short_label": "导入文件",
                "owner_user_id": "u1",
                "visibility": "owner",
                "status": "running",
                "phase": "running",
                "current": 0,
                "total": 0,
                "message": "处理中",
                "result_summary": {},
                "affected_domains": ["imports_etc_invoices"],
                "route": "/imports/etc-invoices",
            }
        )

        payload = job.to_payload()

        self.assertEqual(payload["affected_domains"], ["imports_etc_invoices"])
        self.assertEqual(payload["route"], "/imports/etc-invoices")


class AppStatusArchitectureBoundaryTests(unittest.TestCase):
    def test_app_status_server_integration_uses_public_runtime_snapshot_boundary(self) -> None:
        source = Path("backend/src/fin_ops_platform/app/server.py").read_text(encoding="utf-8")
        method_start = source.index("    def _app_status_runtime_statuses")
        method_end = source.index("    def _apply_workbench_generation_health", method_start)
        method_source = source[method_start:method_end]

        self.assertNotIn("AppStatusRuntimeReader", source)
        self.assertNotIn("_connection", method_source)
        self.assertIn("app_status_runtime_snapshot", method_source)

    def test_app_status_overview_service_does_not_contain_sql(self) -> None:
        source = Path("backend/src/fin_ops_platform/services/app_status_overview_service.py").read_text(encoding="utf-8")

        self.assertNotIn("from job.", source.lower())
        self.assertNotIn("select ", source.lower())


class AppStatusApiContractTests(unittest.TestCase):
    def test_app_health_response_includes_app_status_overview(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn("app_status", payload)
        self.assertEqual(payload["app_status"]["version"], 1)
        self.assertEqual(payload["app_status"]["overall"]["color"], "green")
        self.assertEqual(payload["app_status"]["overall"]["level"], "ok")
        self.assertEqual(
            {domain["route"] for domain in payload["app_status"]["domains"]},
            FRONTEND_ROUTES,
        )


if __name__ == "__main__":
    unittest.main()
