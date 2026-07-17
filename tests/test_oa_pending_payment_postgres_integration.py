from __future__ import annotations

from dataclasses import replace
from http import HTTPStatus
import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.oa_pending_payment_read_model_refresh import (
    OaPendingPaymentReadModelRefreshService,
)
from fin_ops_platform.services.oa_pending_payment_read_model_repository import (
    OaPendingPaymentReadModelRepositoryPort,
)
from fin_ops_platform.services.oa_pending_payment_read_model_service import OaPendingPaymentReadModelService
from fin_ops_platform.services.oa_pending_payment_sql_projection import (
    OaPendingPaymentSqlProjectionBuilder,
    oa_pending_payment_base_source_versions,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class OaPendingPaymentPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.queue = RuntimeQueueRepository(self.connection)
        self.read_repository = PostgresReadModelRepository(self.connection)
        self.pending_relations = PostgresOaPendingPaymentRelationRepository(self.connection)

    def test_identical_canonical_commit_keeps_projection_and_status_rows_unchanged(self) -> None:
        source_snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            queue_repository=self.queue,
            pending_relation_repository=self.pending_relations,
        )
        payment_statuses = {
            "flow-integration-1": OAPaymentStatusRecord(
                flow_id="flow-integration-1",
                pay_status=0,
            )
        }

        first = source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[_record()],
            admission_records=[_record()],
            payment_statuses=payment_statuses,
        )
        before = self.connection.fetch_one(
            """
            select
                application.updated_at as application_updated_at,
                status.updated_at as status_updated_at,
                (select count(*) from job.outbox_events) as outbox_count
            from app.oa_applications application
            join app.oa_pending_payment_status_snapshots status
              on status.tenant_id = 'default'
             and status.flow_id = 'flow-integration-1'
            where application.row_id = 'oa-integration-1'
            """
        )

        second = source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[_record()],
            admission_records=[_record()],
            payment_statuses=payment_statuses,
        )
        after = self.connection.fetch_one(
            """
            select
                application.updated_at as application_updated_at,
                status.updated_at as status_updated_at,
                (select count(*) from job.outbox_events) as outbox_count
            from app.oa_applications application
            join app.oa_pending_payment_status_snapshots status
              on status.tenant_id = 'default'
             and status.flow_id = 'flow-integration-1'
            where application.row_id = 'oa-integration-1'
            """
        )

        self.assertEqual(first.completed_projection_changed_scopes, ("2026-05",))
        self.assertEqual(first.oa_pending_payment_changed_scopes, ("2026-05",))
        self.assertEqual(first.upserted_completed_count, 1)
        self.assertEqual(second.completed_projection_changed_scopes, ())
        self.assertEqual(second.oa_pending_payment_changed_scopes, ())
        self.assertEqual(second.upserted_completed_count, 0)
        self.assertEqual(after, before)

    def test_admission_only_commit_preserves_stable_completed_fact_and_never_enqueues_shared_read_models(self) -> None:
        source_snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            queue_repository=self.queue,
            pending_relation_repository=self.pending_relations,
        )
        completed_record = _record()
        record = replace(_in_progress_record(), amount="", applicant="", reason="")
        payment_statuses = {
            "flow-integration-1": OAPaymentStatusRecord(
                flow_id="flow-integration-1",
                pay_status=0,
            ),
            "flow-in-progress-1": OAPaymentStatusRecord(
                flow_id="flow-in-progress-1",
                pay_status=0,
            )
        }

        source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[completed_record],
            admission_records=[completed_record, record],
            payment_statuses=payment_statuses,
        )
        initial_event = self.queue.claim_next(
            "oa-admission-isolation-integration",
            event_types=["oa_pending_payment.read_model.refresh"],
        )
        self.assertIsNotNone(initial_event)
        assert initial_event is not None
        self.assertTrue(
            self.queue.complete(
                initial_event.event_id,
                "oa-admission-isolation-integration",
                result_payload={"published": True},
            )
        )
        before = self.connection.fetch_one(
            """
            select
                admission.updated_at as admission_updated_at,
                admission.amount as admission_amount,
                status.updated_at as status_updated_at,
                application.updated_at as application_updated_at,
                (select count(*) from job.outbox_events) as outbox_count,
                (select count(*) from app.oa_applications) as completed_projection_count
            from app.oa_pending_payment_admissions admission
            join app.oa_pending_payment_status_snapshots status
              on status.tenant_id = admission.tenant_id
             and status.flow_id = 'flow-in-progress-1'
            join app.oa_applications application
              on application.row_id = 'oa-integration-1'
            where admission.tenant_id = 'default'
              and admission.oa_id = 'oa-in-progress-1'
            """
        )
        before_outbox_ids = {
            str(row["id"])
            for row in self.connection.fetch_all("select id from job.outbox_events")
        }

        changed_admission = replace(record, reason="进行中 OA admission 隔离（已更新）")
        admission_only = source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[completed_record],
            admission_records=[completed_record, changed_admission],
            payment_statuses=payment_statuses,
        )
        after_admission_change = self.connection.fetch_one(
            """
            select
                admission.updated_at as admission_updated_at,
                admission.amount as admission_amount,
                status.updated_at as status_updated_at,
                application.updated_at as application_updated_at,
                (select count(*) from job.outbox_events) as outbox_count,
                (select count(*) from app.oa_applications) as completed_projection_count
            from app.oa_pending_payment_admissions admission
            join app.oa_pending_payment_status_snapshots status
              on status.tenant_id = admission.tenant_id
             and status.flow_id = 'flow-in-progress-1'
            join app.oa_applications application
              on application.row_id = 'oa-integration-1'
            where admission.tenant_id = 'default'
              and admission.oa_id = 'oa-in-progress-1'
            """
        )
        incremental_outbox_rows = [
            row
            for row in self.connection.fetch_all(
                """
                select id, event_type, scope_type, scope_key
                from job.outbox_events
                order by available_at, created_at, id
                """,
            )
            if str(row["id"]) not in before_outbox_ids
        ]

        identical = source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[completed_record],
            admission_records=[completed_record, changed_admission],
            payment_statuses=payment_statuses,
        )
        after_identical = self.connection.fetch_one(
            """
            select
                admission.updated_at as admission_updated_at,
                admission.amount as admission_amount,
                status.updated_at as status_updated_at,
                application.updated_at as application_updated_at,
                (select count(*) from job.outbox_events) as outbox_count,
                (select count(*) from app.oa_applications) as completed_projection_count
            from app.oa_pending_payment_admissions admission
            join app.oa_pending_payment_status_snapshots status
              on status.tenant_id = admission.tenant_id
             and status.flow_id = 'flow-in-progress-1'
            join app.oa_applications application
              on application.row_id = 'oa-integration-1'
            where admission.tenant_id = 'default'
              and admission.oa_id = 'oa-in-progress-1'
            """
        )

        self.assertEqual(admission_only.completed_projection_changed_scopes, ())
        self.assertEqual(admission_only.oa_pending_payment_changed_scopes, ("2026-05",))
        self.assertEqual(identical.completed_projection_changed_scopes, ())
        self.assertEqual(identical.oa_pending_payment_changed_scopes, ())
        self.assertEqual(after_admission_change["application_updated_at"], before["application_updated_at"])
        self.assertEqual(after_admission_change["status_updated_at"], before["status_updated_at"])
        self.assertNotEqual(after_admission_change["admission_updated_at"], before["admission_updated_at"])
        self.assertEqual(after_identical, after_admission_change)
        self.assertIsNone(before["admission_amount"])
        self.assertEqual(int(before["completed_projection_count"]), 1)
        self.assertEqual(
            [
                (row["event_type"], row["scope_type"], row["scope_key"])
                for row in incremental_outbox_rows
            ],
            [("oa_pending_payment.read_model.refresh", "oa_pending_payment", "2026-05")],
        )

    def test_in_progress_to_completed_removes_admission_and_reports_shared_fact_change(self) -> None:
        source_snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            queue_repository=self.queue,
            pending_relation_repository=self.pending_relations,
        )
        in_progress = _in_progress_record()
        completed = replace(in_progress, workflow_status="completed")
        payment_statuses = {
            "flow-in-progress-1": OAPaymentStatusRecord(
                flow_id="flow-in-progress-1",
                pay_status=0,
            )
        }
        source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[],
            admission_records=[in_progress],
            payment_statuses=payment_statuses,
        )

        transitioned = source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[completed],
            admission_records=[completed],
            payment_statuses=payment_statuses,
        )
        counts = self.connection.fetch_one(
            """
            select
                (select count(*) from app.oa_applications) as completed_projection_count,
                (select count(*) from app.oa_pending_payment_admissions) as admission_count
            """
        )

        self.assertEqual(transitioned.completed_projection_changed_scopes, ("2026-05",))
        self.assertEqual(transitioned.oa_pending_payment_changed_scopes, ("2026-05",))
        self.assertEqual(transitioned.admission_count, 0)
        self.assertEqual(int(counts["completed_projection_count"]), 1)
        self.assertEqual(int(counts["admission_count"]), 0)

    def test_canonical_commit_reaches_fresh_rows_and_etag_through_durable_worker_chain(self) -> None:
        source_snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            queue_repository=self.queue,
            pending_relation_repository=self.pending_relations,
        )
        source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            projection_records=[_record()],
            admission_records=[_record()],
            payment_statuses={
                "flow-integration-1": OAPaymentStatusRecord(
                    flow_id="flow-integration-1",
                    pay_status=0,
                )
            },
        )
        service = OaPendingPaymentReadModelService(
            repository=OaPendingPaymentReadModelRepositoryPort(self.read_repository),
            queue_repository=self.queue,
            source_versions_provider=oa_pending_payment_base_source_versions,
        )
        query = {"month": ["2026-05"], "page": ["1"], "page_size": ["20"]}

        non_fresh = service.conditional_rows(
            query,
            tenant_id="default",
            if_none_match=None,
        )
        self.assertEqual(non_fresh.status, HTTPStatus.ACCEPTED)
        self.assertEqual(non_fresh.payload["rows"], [])
        self.assertEqual(
            non_fresh.payload["operationBarrierTargets"],
            [{"readModelKey": "oa_pending_payment", "scopeKey": "2026-05"}],
        )

        event = self.queue.claim_next(
            "oa-pending-payment-integration",
            event_types=["oa_pending_payment.read_model.refresh"],
        )
        self.assertIsNotNone(event)
        assert event is not None
        result = OaPendingPaymentReadModelRefreshService(
            projection_builder=OaPendingPaymentSqlProjectionBuilder(
                connection=self.connection,
                read_model_repository=self.read_repository,
            ),
            queue_repository=self.queue,
        ).handle_runtime_event(event)
        self.assertTrue(result["published"])
        self.assertEqual(result["row_count"], 1)
        self.assertTrue(
            self.queue.complete(
                event.event_id,
                "oa-pending-payment-integration",
                result_payload=result,
            )
        )

        state = OaPendingPaymentReadModelRepositoryPort(self.read_repository).query_state(
            scope_key="2026-05",
            tenant_id="default",
            base_source_versions=oa_pending_payment_base_source_versions(),
        )
        fresh = service.conditional_rows(
            query,
            tenant_id="default",
            if_none_match=None,
        )
        not_modified = service.conditional_rows(
            query,
            tenant_id="default",
            if_none_match=fresh.etag,
        )

        self.assertEqual(state["status"], "fresh")
        self.assertEqual(state["blocking_scope_keys"], [])
        self.assertEqual(state["stale_reasons"], [])
        self.assertEqual(
            state["expected_source_versions_by_scope"]["2026-05"],
            state["source_versions_by_scope"]["2026-05"],
        )
        self.assertEqual(fresh.status, HTTPStatus.OK)
        self.assertEqual(fresh.payload["read_model_status"], "fresh")
        self.assertEqual(len(fresh.payload["rows"]), 1)
        self.assertIsNotNone(fresh.etag)
        self.assertEqual(not_modified.status, HTTPStatus.NOT_MODIFIED)
        self.assertEqual(not_modified.payload, {})


def _record() -> OAApplicationRecord:
    return OAApplicationRecord(
        id="oa-integration-1",
        month="2026-05",
        section="unpaired",
        case_id=None,
        applicant="集成测试申请人",
        project_name="集成测试项目",
        apply_type="支付申请",
        amount="100.00",
        counterparty_name="集成测试供应商",
        reason="真实 PostgreSQL 闭环",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status="completed",
        detail_fields={
            "Mongo文档ID": "flow-integration-1",
            "paymentFlowId": "flow-integration-1",
        },
    )


def _in_progress_record() -> OAApplicationRecord:
    return OAApplicationRecord(
        id="oa-in-progress-1",
        month="2026-05",
        section="unpaired",
        case_id=None,
        applicant="集成测试进行中申请人",
        project_name="集成测试项目",
        apply_type="支付申请",
        amount="88.00",
        counterparty_name="集成测试供应商",
        reason="进行中 OA admission 隔离",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status="in_progress",
        detail_fields={
            "Mongo文档ID": "flow-in-progress-1",
            "paymentFlowId": "flow-in-progress-1",
        },
    )


if __name__ == "__main__":
    unittest.main()
