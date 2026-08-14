from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from uuid import uuid4

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.turnover_ledger_write_uow import TurnoverLedgerWriteUnitOfWork
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork
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
        self.run_id = uuid4().hex
        self.actor_id = f"phase20-postgres-test-{self.run_id}"

    def tearDown(self) -> None:
        self.connection.execute(
            "delete from app.workbench_idempotency_records where actor_id = %s",
            (self.actor_id,),
        )
        truncate_test_database(self.database_url)

    def test_three_registered_profile_pairs_commit_idempotently_without_write_fanout(self) -> None:
        pairs = self._profile_pairs()
        self.assertEqual(pairs, EXPECTED_PROFILE_PAIRS)
        checkpoint_keys: list[str] = []

        for shape_index, (shape, profiles) in enumerate(pairs.items(), start=1):
            month = f"2026-{shape_index:02d}"
            for direction, profile in zip(("confirm", "withdraw"), profiles, strict=True):
                with self.subTest(shape=shape, direction=direction):
                    idempotency_key = self._run_checkpoint(
                        shape=shape,
                        direction=direction,
                        profile=profile,
                        month=month,
                    )
                    checkpoint_keys.append(idempotency_key)

        self.assertEqual(len(checkpoint_keys), len(set(checkpoint_keys)))
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
        self.assertEqual(
            self.connection.fetch_one("select count(*)::integer as count from job.outbox_events")["count"],
            0,
        )
        self.assertIsNone(
            self.connection.fetch_one("select to_regclass('job.read_model_dirty_scopes') as relation")["relation"]
        )

    def test_relation_command_delta_appends_history_without_rewriting_existing_events(self) -> None:
        repository = PostgresWorkbenchRelationRepository(self.connection)
        relation = {
            "case_id": "case-delta",
            "relation_mode": "manual_confirmed",
            "status": "active",
            "month_scope": "2026-02",
            "row_ids": ["bank-delta", "oa-delta"],
            "row_types": ["bank", "oa"],
        }
        existing_history = [
            {
                "case_id": "case-delta",
                "operation_id": f"existing-{index}",
                "operation_type": "manual_confirmed",
                "before_relations": [],
                "after_relations": [relation],
            }
            for index in range(25)
        ]
        repository.save_workbench_pair_relations(
            {
                "pair_relations": {"case-delta": relation},
                "pair_relation_history": existing_history,
            },
            changed_case_ids={"case-delta"},
        )
        new_history = {
            "case_id": "case-delta",
            "operation_id": "new-operation",
            "operation_type": "metadata_updated",
            "before_relations": [relation],
            "after_relations": [relation],
        }

        repository.save_workbench_pair_relation_delta(
            {
                "pair_relations": {"case-delta": relation},
                "pair_relation_history": [new_history],
            },
            changed_case_ids={"case-delta"},
        )
        repository.save_workbench_pair_relation_delta(
            {
                "pair_relations": {"case-delta": relation},
                "pair_relation_history": [new_history],
            },
            changed_case_ids={"case-delta"},
        )

        history_count = self.connection.fetch_one(
            "select count(*)::integer as count from app.workbench_pair_relation_history where case_id = %s",
            ("case-delta",),
        )
        active_snapshot = repository.load_active_workbench_pair_relations_for_row_ids(
            ["bank-delta"],
            case_ids=["case-delta"],
        )
        self.assertEqual(history_count["count"], 26)
        self.assertEqual(sorted(active_snapshot["pair_relations"]), ["case-delta"])
        self.assertNotIn("pair_relation_history", active_snapshot)

    def _run_checkpoint(
        self,
        *,
        shape: str,
        direction: str,
        profile: str,
        month: str,
    ) -> str:
        idempotency_key = f"phase20:{self.run_id}:{shape}:{direction}"
        command = self._command(
            shape=shape,
            direction=direction,
            month=month,
            idempotency_key=idempotency_key,
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
                idempotency_store=PostgresWorkbenchIdempotencyRepository(self.connection),
            )

        result = uow.run(
            command,
            lambda _context: {
                "case_id": f"phase20:{shape}",
                "affected_scope_keys": [month],
            },
        )
        self.assertEqual(result["outbox_event_ids"], [])
        self.assertEqual(
            self.connection.fetch_one("select count(*)::integer as count from job.outbox_events")["count"],
            0,
        )
        return idempotency_key

    @staticmethod
    def _command(
        *,
        shape: str,
        direction: str,
        month: str,
        idempotency_key: str,
        actor_id: str,
        profile: str,
    ) -> _CheckpointCommand:
        metadata: dict[str, object] = {
            "source": "phase20_reversible_relation_closure",
            "fixture_ownership": "test_owned",
            "shape": shape,
        }
        action_name = f"{direction}_link"
        if profile == "turnover_relation_confirm_cross_page":
            action_name = "turnover_relation_zero_difference_closure"
        elif profile == "turnover_relation_withdraw_cross_page":
            action_name = "turnover_relation_withdraw"
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
