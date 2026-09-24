from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from psycopg.errors import CheckViolation

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    InMemoryCostStatisticsManualAllocationRepository,
    PostgresCostStatisticsManualAllocationRepository,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def decision_values(**changes):
    return {
        "relation_case_id": "cost-decision", "decision_mode": "manual", "relation_version": 1,
        "source_fingerprint": "a" * 64, "oa_total": "100.00", "gross_outflow_total": "100.00",
        "wrong_payment_refund_total": "0.00", "net_outflow_total": "100.00",
        "allocations": [{"unit_id": "oa-a", "amount": "100.00"}],
        "source_allocations": {"cost_lines": [{"unit_id": "oa-a", "bank_transaction_id": "bank-a", "amount": "100.00"}],
                               "refund_links": [], "non_cost_lines": []},
        "manual_items": [], "oa_amount_locks": {"oa-a": True}, "oa_cost_tag_overrides": [],
        "non_cost_amount": "0.00", "non_cost_reason": "", "expected_version": 0, "actor_id": "tester", **changes,
    }


class InMemoryCostDecisionStorageTests(TestCase):
    def test_versions_survive_manual_automatic_manual_cycle(self):
        repository = InMemoryCostStatisticsManualAllocationRepository()
        first = repository.save(**decision_values())
        self.assertEqual(first["version"], 1)
        automatic = repository.retire_to_automatic(relation_case_id="cost-decision", expected_version=1, actor_id="migration")
        self.assertEqual((automatic["decision_mode"], automatic["version"]), ("automatic", 2))
        self.assertIsNone(repository.retire_to_automatic(relation_case_id="cost-decision", expected_version=2, actor_id="migration"))
        self.assertIsNone(repository.save(**decision_values()))
        self.assertIsNone(repository.save(**decision_values(expected_version=1)))
        manual = repository.save(**decision_values(expected_version=2))
        self.assertEqual((manual["decision_mode"], manual["version"]), ("manual", 3))
        self.assertEqual(repository.list_by_case_ids(["cost-decision"])["cost-decision"]["version"], 3)

    def test_unknown_mode_fails_before_writing(self):
        repository = InMemoryCostStatisticsManualAllocationRepository()
        with self.assertRaisesRegex(ValueError, "decision mode"):
            repository.save(**decision_values(decision_mode="unknown"))
        self.assertEqual(repository.list_by_case_ids(["cost-decision"]), {})


class PostgresCostDecisionStorageTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)
        cls.connection = PostgresConnection(PostgresSettings(database_url=cls.database_url, pool_enabled=False))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        truncate_test_database(self.database_url)
        self.repository = PostgresCostStatisticsManualAllocationRepository(self.connection)

    def tearDown(self):
        truncate_test_database(self.database_url)

    def test_versions_and_payload_survive_retirement_and_stale_writes_are_rejected(self):
        first = self.repository.save(**decision_values())
        self.assertEqual(first["decision_mode"], "manual")
        self.assertIsNone(self.repository.retire_to_automatic(relation_case_id="cost-decision", expected_version=0, actor_id="migration"))
        automatic = self.repository.retire_to_automatic(relation_case_id="cost-decision", expected_version=1, actor_id="migration")
        self.assertEqual((automatic["decision_mode"], automatic["version"]), ("automatic", 2))
        self.assertEqual(automatic["source_allocations"], first["source_allocations"])
        self.assertIsNone(self.repository.save(**decision_values()))
        self.assertIsNone(self.repository.save(**decision_values(expected_version=1)))
        self.assertIsNone(self.repository.retire_to_automatic(relation_case_id="cost-decision", expected_version=2, actor_id="migration"))
        restored = self.repository.save(**decision_values(expected_version=2))
        self.assertEqual((restored["decision_mode"], restored["version"]), ("manual", 3))
        self.assertEqual(self.repository.list_by_case_ids(["cost-decision"])["cost-decision"]["version"], 3)

    def test_candidates_include_missing_relations_but_exclude_automatic_markers(self):
        self.repository.save(**decision_values())
        self.repository.save(**decision_values(relation_case_id="automatic-case", decision_mode="automatic"))
        self.assertEqual(self.repository.list_decision_candidates(), [{
            "relation_case_id": "cost-decision", "decision_mode": "manual", "version": 1, "relation_status": None,
        }])
        self.assertEqual([row["relation_case_id"] for row in self.repository.list_bank_split_migration_candidates()], ["cost-decision"])

    def test_split_retires_once_and_audits_full_before_and_preserved_revision(self):
        before = self.repository.save(**decision_values())
        with self.connection.transaction() as tx:
            repository = PostgresCostStatisticsManualAllocationRepository(tx)
            self.assertEqual(repository.revoke_for_bank_split(["cost-decision"], actor_id="splitter", parent_id="bank-a"), ["cost-decision"])
            self.assertEqual(repository.revoke_for_bank_split(["cost-decision"], actor_id="splitter", parent_id="bank-a"), [])
        current = self.repository.list_by_case_ids(["cost-decision"])["cost-decision"]
        self.assertEqual((current["decision_mode"], current["version"]), ("automatic", 2))
        events = self.connection.fetch_all("select payload from audit.events where object_id='cost-decision'")
        self.assertEqual(len(events), 1)
        payload = events[0]["payload"]
        self.assertEqual(payload["before"]["source_allocations"], before["source_allocations"])
        self.assertEqual(payload["before"]["unit_allocations"], before["allocations"])
        self.assertEqual(payload["before"]["decision_mode"], "manual")
        self.assertEqual(payload["before"]["version"], 1)
        self.assertEqual(payload["after"], {"decision_mode": "automatic", "version": 2})

    def test_split_audit_failure_rolls_back_decision_and_revision(self):
        self.repository.save(**decision_values())
        with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
            with self.connection.transaction() as tx:
                with patch("fin_ops_platform.services.postgres_repositories.operations_audit.PostgresOperationsAuditRepository.append_operation_event", side_effect=RuntimeError("audit unavailable")):
                    PostgresCostStatisticsManualAllocationRepository(tx).revoke_for_bank_split(["cost-decision"], actor_id="splitter", parent_id="bank-a")
        current = self.repository.list_by_case_ids(["cost-decision"])["cost-decision"]
        self.assertEqual((current["decision_mode"], current["version"]), ("manual", 1))
        self.assertEqual(self.connection.fetch_all("select id from audit.events where object_id='cost-decision'"), [])

    def test_migration_preserves_existing_payload_and_version(self):
        self.repository.save(**decision_values())
        before = self.connection.fetch_one("select to_jsonb(t) - 'decision_mode' as payload from app.cost_statistics_manual_allocations t")["payload"]
        with self.connection.transaction() as tx:
            tx.execute("alter table app.cost_statistics_manual_allocations drop column decision_mode")
            tx.execute(Path("backend/src/fin_ops_platform/postgres/migrations/0181_cost_statistics_decision_mode.sql").read_text())
        after = self.connection.fetch_one("select to_jsonb(t) as payload from app.cost_statistics_manual_allocations t")["payload"]
        self.assertEqual(after, {**before, "decision_mode": "manual"})
        with self.assertRaises(CheckViolation) as invalid:
            with self.connection.transaction() as tx:
                tx.execute("update app.cost_statistics_manual_allocations set decision_mode='unknown'")
        self.assertEqual(invalid.exception.sqlstate, "23514")
