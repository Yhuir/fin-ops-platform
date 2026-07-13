from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent, RuntimeQueueRepository
from fin_ops_platform.services.turnover_ledger_write_adapters import TurnoverLedgerDirtyOutboxWriter
from fin_ops_platform.services.turnover_ledger_write_uow import TurnoverLedgerWriteUnitOfWork
from fin_ops_platform.services.workbench_uow import (
    RuntimeQueueReadModelRefreshWriter,
    WorkbenchWriteUnitOfWork,
)
from fin_ops_platform.tools import write_operation_slo_audit
from tests.postgres_test_utils import (
    apply_test_migrations,
    assert_safe_test_database_url,
    require_postgres_test_database_url,
    truncate_test_database,
)


IMPACT_MATRIX_PATH = Path("docs/dev/write-operation-impact-matrix.json")
EXPECTED_PROFILE_PAIRS = {
    "bank_invoice": (
        "workbench_relation_confirm_bank_invoice_cross_page",
        "workbench_relation_withdraw_bank_invoice_cross_page",
    ),
    "bank_turnover": (
        "turnover_relation_confirm_cross_page",
        "turnover_relation_withdraw_cross_page",
    ),
    "bank_oa_invoice": (
        "workbench_relation_confirm_cross_page",
        "workbench_relation_withdraw_cross_page",
    ),
}


@dataclass(frozen=True)
class _CheckpointCommand:
    action_name: str
    scope_keys: list[str]
    idempotency_key: str
    payload: dict[str, object]
    refresh_metadata: dict[str, object]
    tenant_id: str = "default"
    actor_id: str = ""
    expected_versions: dict[str, object] = field(default_factory=dict)
    refresh_requests: list[dict[str, object]] = field(default_factory=list)


class ReversibleRelationPostgresSafetyTests(unittest.TestCase):
    def test_disposable_database_guard_rejects_reserved_database(self) -> None:
        with self.assertRaisesRegex(AssertionError, "reserved database fin_ops"):
            assert_safe_test_database_url("postgresql://finops:secret@localhost/fin_ops")


class ReversibleRelationClosurePostgresTests(unittest.TestCase):
    """Opt-in durable event-correlation proof; business closure stays in the HTTP runner."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.queue = RuntimeQueueRepository(self.connection)
        self.run_id = uuid4().hex
        self.actor_id = f"phase20-postgres-test-{self.run_id}"

    def tearDown(self) -> None:
        self.connection.execute(
            "delete from app.workbench_idempotency_records where actor_id = %s",
            (self.actor_id,),
        )
        truncate_test_database(self.database_url)

    def test_three_registered_profile_pairs_bind_each_checkpoint_to_exact_durable_events(self) -> None:
        pairs = self._profile_pairs()
        self.assertEqual(pairs, EXPECTED_PROFILE_PAIRS)
        checkpoint_event_ids: list[str] = []

        for shape_index, (shape, profiles) in enumerate(pairs.items(), start=1):
            month = f"2026-{shape_index:02d}"
            for direction, profile in zip(("confirm", "withdraw"), profiles, strict=True):
                with self.subTest(shape=shape, direction=direction):
                    event_ids = self._run_checkpoint(
                        shape=shape,
                        direction=direction,
                        profile=profile,
                        month=month,
                    )
                    self.assertTrue(set(event_ids).isdisjoint(checkpoint_event_ids))
                    checkpoint_event_ids.extend(event_ids)

        self.assertEqual(len(checkpoint_event_ids), len(set(checkpoint_event_ids)))
        self.assertEqual(
            self.connection.fetch_one(
                """
                select count(*)::integer as count
                from app.workbench_idempotency_records
                where status = 'committed' and actor_id = %s
                """,
                (self.actor_id,),
            )["count"],
            6,
        )

    def test_partial_relation_projection_removes_stale_members_from_replaced_group(self) -> None:
        repository = PostgresReadModelRepository(self.connection)
        repository.save_workbench_relation_distribution(
            scope_key="2026-02",
            groups=[
                {
                    "group_id": "turnover:target",
                    "relation_source": "manual",
                    "relation_kind": "turnover_manual_closure",
                    "relation_status": "linked",
                    "oa_row_ids": ["oa-stale"],
                    "bank_transaction_ids": ["bank-target"],
                },
                {
                    "group_id": "case:unrelated",
                    "relation_source": "manual",
                    "relation_kind": "bank_invoice",
                    "relation_status": "linked",
                    "input_invoice_ids": ["invoice-unrelated"],
                },
            ],
            rows=[
                {
                    "row_id": "bank-target",
                    "row_type": "bank_transaction",
                    "relation_status": "linked",
                    "group_ids": ["turnover:target"],
                },
                {
                    "row_id": "oa-stale",
                    "row_type": "oa",
                    "relation_status": "linked",
                    "group_ids": ["turnover:target"],
                },
                {
                    "row_id": "invoice-unrelated",
                    "row_type": "input_invoice",
                    "relation_status": "linked",
                    "group_ids": ["case:unrelated"],
                },
            ],
            source_versions={"workbench_relation_source_version": 1},
        )

        repository.save_workbench_relation_distribution_rows(
            scope_key="2026-02",
            affected_row_ids=["bank-target"],
            groups=[
                {
                    "group_id": "turnover:target",
                    "relation_source": "manual",
                    "relation_kind": "turnover_manual_closure",
                    "relation_status": "linked",
                    "bank_transaction_ids": ["bank-target"],
                }
            ],
            rows=[
                {
                    "row_id": "bank-target",
                    "row_type": "bank_transaction",
                    "relation_status": "linked",
                    "group_ids": ["turnover:target"],
                },
                {
                    "row_id": "oa-stale",
                    "row_type": "oa",
                    "relation_status": "unlinked",
                    "group_ids": [],
                },
            ],
            source_versions={"workbench_relation_source_version": 2},
        )

        rows = self.connection.fetch_all(
            """
            select row_id, group_ids
            from read_model.workbench_relation_rows
            where tenant_id = 'default' and scope_key = '2026-02'
            order by row_id
            """
        )
        groups = self.connection.fetch_all(
            """
            select group_id, oa_row_ids, bank_transaction_ids, input_invoice_ids
            from read_model.workbench_relation_groups
            where tenant_id = 'default' and scope_key = '2026-02'
            order by group_id
            """
        )

        self.assertEqual(
            rows,
            [
                {"row_id": "bank-target", "group_ids": ["turnover:target"]},
                {"row_id": "invoice-unrelated", "group_ids": ["case:unrelated"]},
                {"row_id": "oa-stale", "group_ids": []},
            ],
        )
        self.assertEqual(
            groups,
            [
                {
                    "group_id": "case:unrelated",
                    "oa_row_ids": [],
                    "bank_transaction_ids": [],
                    "input_invoice_ids": ["invoice-unrelated"],
                },
                {
                    "group_id": "turnover:target",
                    "oa_row_ids": [],
                    "bank_transaction_ids": ["bank-target"],
                    "input_invoice_ids": [],
                },
            ],
        )

    def _run_checkpoint(
        self,
        *,
        shape: str,
        direction: str,
        profile: str,
        month: str,
    ) -> list[str]:
        expectations = write_operation_slo_audit.selected_expectations_for_operations([profile])
        expected_scope_types = {expectation.scope_type for expectation in expectations}
        idempotency_key = f"phase20:{self.run_id}:{shape}:{direction}"
        started_at = self.connection.fetch_one("select clock_timestamp() as value")["value"]
        command = self._command(
            shape=shape,
            direction=direction,
            month=month,
            idempotency_key=idempotency_key,
            expected_scope_types=expected_scope_types,
            actor_id=self.actor_id,
            profile=profile,
        )
        if profile.startswith("turnover_relation_"):
            uow = TurnoverLedgerWriteUnitOfWork(
                connection=self.connection,
                relation_repository=SimpleNamespace(),
                extra_repository=SimpleNamespace(),
                settings_port=SimpleNamespace(),
                bankdetail_port=SimpleNamespace(),
                dirty_outbox_writer=TurnoverLedgerDirtyOutboxWriter(
                    queue_repository=self.queue,
                    tenant_id="default",
                    priority="high",
                    trace_id=idempotency_key,
                ),
                stale_precondition_port=SimpleNamespace(assert_current=lambda **_kwargs: None),
                idempotency_store=PostgresWorkbenchIdempotencyRepository(self.connection),
            )
        else:
            uow = WorkbenchWriteUnitOfWork(
                connection=self.connection,
                repository_factory=lambda _transaction: SimpleNamespace(
                    pair_relations=None,
                    exception_cases=None,
                    row_overrides=None,
                    candidate_matches=None,
                ),
                read_model_refresh_writer=RuntimeQueueReadModelRefreshWriter(
                    self.queue,
                    tenant_id="default",
                    priority="high",
                    trace_id=idempotency_key,
                ),
                idempotency_store=PostgresWorkbenchIdempotencyRepository(self.connection),
            )

        result = uow.run(
            command,
            lambda _context: {
                "case_id": f"phase20:{shape}",
                "affected_scope_keys": [month],
            },
        )
        event_ids = write_operation_slo_audit.committed_workbench_outbox_event_ids(
            self.connection,
            tenant_id="default",
            idempotency_key=idempotency_key,
        )
        self.assertEqual(event_ids, result["outbox_event_ids"])

        pending_rows = self._exact_rows(
            started_at=started_at,
            expectations=expectations,
            event_ids=event_ids,
        )
        self.assertEqual({row["event_id"] for row in pending_rows}, set(event_ids))
        self.assertEqual({row["scope_type"] for row in pending_rows}, expected_scope_types)
        self.assertTrue(all(row["event_status"] == "pending" for row in pending_rows))
        self.assertTrue(all(row["dirty_status"] == "pending" for row in pending_rows))
        self.assertTrue(
            any(
                result.status == "fail"
                for result in write_operation_slo_audit.evaluate_operation_expectations(
                    pending_rows,
                    expectations=expectations,
                    target_ms=10_000,
                )
            ),
            "worker-unavailable/pending evidence must fail closed",
        )

        self._drain_events(event_ids)
        fresh_rows = self._exact_rows(
            started_at=started_at,
            expectations=expectations,
            event_ids=event_ids,
        )
        results = write_operation_slo_audit.evaluate_operation_expectations(
            fresh_rows,
            expectations=expectations,
            target_ms=10_000,
        )
        self.assertTrue(results)
        self.assertTrue(all(result.status == "pass" for result in results), results)

        if shape == "bank_invoice" and direction == "confirm":
            self._assert_same_profile_event_cannot_contaminate_checkpoint(
                started_at=started_at,
                expectations=expectations,
                checkpoint_event_ids=event_ids,
            )
        return event_ids

    def _assert_same_profile_event_cannot_contaminate_checkpoint(
        self,
        *,
        started_at: datetime,
        expectations: list[write_operation_slo_audit.OperationExpectation],
        checkpoint_event_ids: list[str],
    ) -> None:
        concurrent = self.queue.enqueue_read_model_refresh(
            scope_type="workbench",
            scope_key="2026-12",
            reason="workbench_relation_changed",
            priority="high",
            trace_id="phase20:concurrent",
            metadata={"action_name": "confirm_link"},
        )
        try:
            exact_rows = self._exact_rows(
                started_at=started_at,
                expectations=expectations,
                event_ids=checkpoint_event_ids,
            )
            unfiltered_rows = write_operation_slo_audit.recent_read_model_refresh_events_since(
                self.connection,
                tenant_id="default",
                started_at=started_at,
                limit=100,
                expectations=expectations,
            )
            self.assertNotIn(concurrent.event_id, {row["event_id"] for row in exact_rows})
            self.assertIn(concurrent.event_id, {row["event_id"] for row in unfiltered_rows})
            self.assertTrue(
                all(
                    result.status == "pass"
                    for result in write_operation_slo_audit.evaluate_operation_expectations(
                        exact_rows,
                        expectations=expectations,
                        target_ms=10_000,
                    )
                )
            )
            self.assertTrue(
                any(
                    result.status == "fail"
                    for result in write_operation_slo_audit.evaluate_operation_expectations(
                        unfiltered_rows,
                        expectations=expectations,
                        target_ms=10_000,
                    )
                ),
                "same-profile pending evidence must fail an uncorrelated audit",
            )
        finally:
            self._drain_events([concurrent.event_id])

    def _exact_rows(
        self,
        *,
        started_at: datetime,
        expectations: list[write_operation_slo_audit.OperationExpectation],
        event_ids: list[str],
    ) -> list[dict[str, object]]:
        return write_operation_slo_audit.recent_read_model_refresh_events_since(
            self.connection,
            tenant_id="default",
            started_at=started_at,
            limit=max(20, len(event_ids) * 2),
            expectations=expectations,
            event_ids=event_ids,
        )

    def _drain_events(self, event_ids: list[str]) -> None:
        worker_id = "phase20-postgres-test-worker"
        for event_id in event_ids:
            event = self.queue.claim_event_by_id(event_id=event_id, worker_id=worker_id)
            self.assertIsNotNone(event, event_id)
            assert isinstance(event, RuntimeQueueEvent)
            self.assertTrue(
                self.queue.complete_read_model_refresh(
                    tenant_id=event.tenant_id,
                    scope_type=str(event.scope_type),
                    scope_key=str(event.scope_key),
                    source_version=event.source_version,
                ),
                event_id,
            )
            self.assertTrue(self.queue.complete(event_id, worker_id), event_id)

    @staticmethod
    def _command(
        *,
        shape: str,
        direction: str,
        month: str,
        idempotency_key: str,
        expected_scope_types: set[str],
        actor_id: str,
        profile: str,
    ) -> _CheckpointCommand:
        downstream_scope_types = sorted(expected_scope_types - {"workbench", "workbench_relation", "pending_invoice"})
        metadata: dict[str, object] = {
            "source": "phase20_reversible_relation_closure",
            "fixture_ownership": "test_owned",
            "shape": shape,
            "downstream_scope_types": downstream_scope_types,
        }
        if "pending_invoice" in expected_scope_types:
            metadata["downstream_scope_types"] = [*downstream_scope_types, "pending_invoice"]
            metadata["pending_invoice_scope_keys"] = [f"expense:all:{month}"]
        action_name = f"{direction}_link"
        reason = "workbench_relation_changed"
        if profile == "turnover_relation_confirm_cross_page":
            action_name = "turnover_relation_zero_difference_closure"
            reason = "turnover_relation_changed"
        elif profile == "turnover_relation_withdraw_cross_page":
            action_name = "turnover_relation_withdraw"
            reason = "turnover_relation_changed"
        refresh_requests = (
            [
                {
                    "scope_type": scope_type,
                    "scope_keys": [month],
                    "reason": reason,
                }
                for scope_type in sorted(expected_scope_types)
            ]
            if profile.startswith("turnover_relation_")
            else []
        )
        return _CheckpointCommand(
            action_name=action_name,
            scope_keys=[month],
            idempotency_key=idempotency_key,
            payload={
                "shape": shape,
                "direction": direction,
                "fixture_ownership": "test_owned",
            },
            refresh_metadata=metadata,
            actor_id=actor_id,
            refresh_requests=refresh_requests,
        )

    @staticmethod
    def _profile_pairs() -> dict[str, tuple[str, str]]:
        payload = json.loads(IMPACT_MATRIX_PATH.read_text(encoding="utf-8"))
        return {
            str(item["shape"]): (
                str(item["confirm_profile"]),
                str(item["withdraw_profile"]),
            )
            for item in payload["reversible_relation_profile_pairs"]
        }


if __name__ == "__main__":
    unittest.main()
