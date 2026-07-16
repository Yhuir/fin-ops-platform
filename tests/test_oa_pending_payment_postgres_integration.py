from __future__ import annotations

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
from fin_ops_platform.services.workbench_relation_read_model_refresh import (
    WorkbenchRelationReadModelRefreshService,
)
from fin_ops_platform.services.workbench_relation_sql_projection import (
    WorkbenchRelationSqlProjectionBuilder,
)
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
            records=[_record()],
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
            records=[_record()],
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

        self.assertEqual(first.affected_scope_keys, ("2026-05",))
        self.assertEqual(first.upserted_completed_count, 1)
        self.assertEqual(second.affected_scope_keys, ())
        self.assertEqual(second.upserted_completed_count, 0)
        self.assertEqual(after, before)

    def test_canonical_commit_reaches_fresh_rows_and_etag_through_durable_worker_chain(self) -> None:
        self.read_repository.mark_workbench_relation_scope_empty(
            scope_key="2026-05",
            tenant_id="default",
            source_versions={"integration_relation_version": 1},
        )
        source_snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            queue_repository=self.queue,
            pending_relation_repository=self.pending_relations,
        )
        source_snapshot.commit_authoritative_snapshot(
            scope_key="2026-05",
            tenant_id="default",
            records=[_record()],
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

        relation_event = self.queue.claim_next(
            "workbench-relation-integration",
            event_types=["workbench_relation.read_model.refresh"],
        )
        self.assertIsNotNone(relation_event)
        assert relation_event is not None
        relation_result = WorkbenchRelationReadModelRefreshService(
            projection_builder=WorkbenchRelationSqlProjectionBuilder(
                connection=self.connection,
                read_model_repository=self.read_repository,
            ),
            queue_repository=self.queue,
        ).handle_runtime_event(relation_event)
        self.assertTrue(
            self.queue.complete(
                relation_event.event_id,
                "workbench-relation-integration",
                result_payload=relation_result,
            )
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


if __name__ == "__main__":
    unittest.main()
