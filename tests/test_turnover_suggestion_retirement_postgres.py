from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.page_business_audit import audit_page_canonical_data
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.turnover_suggestion_retirement import (
    PostgresTurnoverSuggestionRetirementRepository,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class TurnoverSuggestionRetirementPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.addCleanup(truncate_test_database, self.database_url)
        self.parent = str(uuid4())
        self.unsplit = str(uuid4())
        self.children = [str(uuid4()), str(uuid4())]
        for identity, legacy in [(self.parent, "old-parent"), (self.unsplit, "unsplit")]:
            self.connection.execute("""INSERT INTO app.bank_transactions
                (id,legacy_mongo_id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,status)
                VALUES (%s::uuid,%s,'TEST','outflow','测试',10,-10,'2026-09-01','2026-09-01','active')""", (identity, legacy))
        self.connection.execute("INSERT INTO app.bank_transaction_split_sets(bank_transaction_id,version,updated_by) VALUES (%s::uuid,1,'tester')", (self.parent,))
        for position, child in enumerate(self.children):
            self.connection.execute("""INSERT INTO app.bank_transaction_split_items(id,bank_transaction_id,category_code,amount,position)
                VALUES (%s::uuid,%s::uuid,'test-category',5,%s)""", (child, self.parent, position))

    def insert_relation(self, identity, *, source="system", status="suggested", member="old-parent"):
        payload = {"relation_id": identity, "source": source, "status": status, "bank_row_ids": [member]}
        self.connection.execute("""INSERT INTO app.turnover_relations(relation_id,status,raw_payload)
            VALUES (%s,%s,%s)""", (identity, status, jsonb({"normalized_payload": payload})))

    def run_owner(self, *, apply=False):
        with self.connection.transaction() as transaction:
            transaction.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if apply else
                                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return PostgresTurnoverSuggestionRetirementRepository(transaction).run(apply=apply, actor_id="tester")

    def test_audit_ignores_rebuilt_system_suggestions_but_checks_manual_and_confirmed_history(self):
        self.insert_relation("obsolete-system")
        self.insert_relation("system-unknown", member="missing")
        report = audit_page_canonical_data(self.connection, domain_key="turnover_ledger")
        self.assertEqual(report["overall_status"], "pass")
        for identity, source, status in [("manual-missing", "manual", "suggested"),
                                        ("manual-stale", "manual", "stale"),
                                        ("confirmed-missing", "system", "confirmed"),
                                        ("withdrawn-missing", "system", "withdrawn")]:
            self.insert_relation(identity, source=source, status=status, member="missing")
        self.insert_relation("manual-valid-child", source="manual", status="confirmed", member=self.children[0])
        report = audit_page_canonical_data(self.connection, domain_key="turnover_ledger")
        issues = [issue for issue in report["issues"] if issue["code"] == "turnover_ledger_manual_relation_bank_member_missing"]
        self.assertEqual({issue["subject_id"] for issue in issues},
                         {"manual-missing", "manual-stale", "confirmed-missing", "withdrawn-missing"})
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")

    def test_preview_apply_idempotency_and_precise_exclusions_preserve_before_audit(self):
        self.insert_relation("obsolete-system")
        self.insert_relation("obsolete-canonical", member=self.parent)
        self.insert_relation("unsplit-system", member="unsplit")
        self.insert_relation("manual", source="manual")
        self.insert_relation("confirmed", status="confirmed")
        self.insert_relation("withdrawn", status="withdrawn")
        self.insert_relation("system-missing", member="missing")
        self.insert_relation("system-current-child", member=self.children[0])
        self.insert_relation("system-with-extra")
        self.connection.execute("INSERT INTO app.turnover_ledger_extras(ledger_key,extra_payload) VALUES ('system-with-extra','{}')")
        self.insert_relation("system-with-event")
        self.connection.execute("""INSERT INTO app.turnover_relation_events(turnover_relation_id,relation_id,event_type)
            SELECT id,relation_id,'existing-event' FROM app.turnover_relations WHERE relation_id='system-with-event'""")
        before = self.connection.fetch_all("SELECT relation_id,to_jsonb(t) AS fact FROM app.turnover_relations t ORDER BY relation_id")
        preview = self.run_owner()
        self.assertEqual({row["relation_id"] for row in preview["candidates"]}, {"obsolete-system", "obsolete-canonical"})
        self.assertEqual(preview["retired_relation_ids"], [])
        self.assertEqual(self.connection.fetch_all("SELECT relation_id,to_jsonb(t) AS fact FROM app.turnover_relations t ORDER BY relation_id"), before)
        applied = self.run_owner(apply=True)
        self.assertEqual(set(applied["retired_relation_ids"]), {"obsolete-system", "obsolete-canonical"})
        for row in before:
            current = self.connection.fetch_one("SELECT to_jsonb(t) AS fact FROM app.turnover_relations t WHERE relation_id=%s", (row["relation_id"],))
            if row["relation_id"] in applied["retired_relation_ids"]:
                self.assertIsNone(current)
                audit = self.connection.fetch_one("SELECT payload FROM audit.events WHERE object_id=%s", (row["relation_id"],))["payload"]
                self.assertEqual(audit["before"], row["fact"])
                self.assertEqual(audit["after"], {"retired": True, "relation_id": row["relation_id"]})
            else:
                self.assertEqual(current["fact"], row["fact"])
        self.assertEqual(self.run_owner(apply=True)["affected_count"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], 2)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.bank_transactions")["n"], 2)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.bank_transaction_split_items")["n"], 2)

    def test_canonical_load_save_cannot_revive_retired_suggestions(self):
        self.insert_relation("obsolete-system")
        self.assertEqual(self.run_owner(apply=True)["retired_relation_ids"], ["obsolete-system"])
        owner = PostgresWorkbenchRepository(self.connection)
        snapshot = owner.load_turnover_relations()
        self.assertEqual(snapshot["relations"], [])
        owner.save_turnover_relations(snapshot)
        self.assertIsNone(self.connection.fetch_one("SELECT relation_id FROM app.turnover_relations WHERE relation_id='obsolete-system'"))
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], 1)

    def test_rollback_and_incomplete_split_do_not_retire(self):
        self.insert_relation("obsolete-system")
        with self.assertRaisesRegex(RuntimeError, "rollback test"):
            with self.connection.transaction() as transaction:
                result = PostgresTurnoverSuggestionRetirementRepository(transaction).run(apply=True, actor_id="tester")
                self.assertEqual(result["retired_relation_ids"], ["obsolete-system"])
                raise RuntimeError("rollback test")
        self.assertEqual(self.connection.fetch_one("SELECT status FROM app.turnover_relations")["status"], "suggested")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], 0)
        self.connection.execute("UPDATE app.bank_transaction_split_items SET amount=4 WHERE id=%s::uuid", (self.children[0],))
        self.assertEqual(self.run_owner(apply=True)["affected_count"], 0)

    def test_retirement_executes_against_pre_0180_schema(self):
        self.insert_relation("obsolete-system")
        view_sql = (Path(__file__).resolve().parents[1] / "backend/src/fin_ops_platform/postgres/migrations/0179_bank_transaction_units.sql").read_text()
        with self.assertRaisesRegex(RuntimeError, "restore current test schema"):
            with self.connection.transaction() as transaction:
                transaction.execute("DROP VIEW app.bank_transaction_units")
                transaction.execute("ALTER TABLE app.bank_transaction_split_items DROP COLUMN category_payload")
                transaction.execute(view_sql)
                result = PostgresTurnoverSuggestionRetirementRepository(transaction).run(apply=True, actor_id="tester")
                self.assertEqual(result["retired_relation_ids"], ["obsolete-system"])
                raise RuntimeError("restore current test schema")
        self.assertEqual(self.connection.fetch_one("SELECT status FROM app.turnover_relations")["status"], "suggested")
