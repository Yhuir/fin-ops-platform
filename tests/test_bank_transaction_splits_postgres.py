from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import PostgresBankDetailsCanonicalQueryRepository
from fin_ops_platform.services.bank_transaction_split_relation_service import BankTransactionSplitRelationService
from fin_ops_platform.services.bank_transaction_split_service import (
    BankTransactionSplitError,
    BankTransactionSplitService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_transaction_splits import (
    PostgresBankTransactionSplitRepository,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)
from fin_ops_platform.services.postgres_repositories.turnover_bank_split import PostgresTurnoverBankSplitRepository
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class BankTransactionSplitPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.parent = str(uuid4())
        self.settings = {"access_control_version": 1, "page_access_accounts": [], "bank_transaction_tags": {"version": 1, "definitions": [
            {"code": "test_principal", "label": "本金", "path": ["往来", "本金"], "status": "active", "source": "custom", "rules": {}, "output_primary_label": "往来", "output_sub_label": "本金", "turnover_role": "external_turnover"},
            {"code": "test_interest", "label": "利息", "path": ["费用", "利息"], "status": "active", "source": "custom", "rules": {}, "output_primary_label": "费用", "output_sub_label": "利息"},
        ]}}
        self.connection.execute("INSERT INTO app.app_settings(settings_key,settings_payload) VALUES ('app_settings',%s) ON CONFLICT(settings_key) DO UPDATE SET settings_payload=excluded.settings_payload", (jsonb(self.settings),))
        self.connection.execute(
            """INSERT INTO app.bank_transactions(id,legacy_mongo_id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,txn_date,txn_month,balance,currency,status)
               VALUES (%s::uuid,'txn-split-test','TEST0001','outflow','匿名测试',1001497.22,-1001497.22,'2026-09-01','2026-09-01',2000.00,'CNY','pending')""", (self.parent,))
        self.published = []
        self.relations = BankTransactionSplitRelationService(
            relation_repository_factory=PostgresWorkbenchRelationRepository,
            settings_snapshot_provider=lambda tx: AppSettingsService.bank_category_relation_policy_snapshot(PostgresBankDetailsCanonicalQueryRepository.settings_payload(tx)),
            effective_category_rows=PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows,
            relation_delta_publisher=lambda *args, **kwargs: self.published.append((args, kwargs)),
            allocation_repository_factory=PostgresCostStatisticsManualAllocationRepository,
            batch_repository_factory=PostgresWorkbenchRepository,
            turnover_split_migrator=lambda tx, **kwargs: PostgresTurnoverBankSplitRepository(tx).apply(**kwargs),
        )
        self.service = BankTransactionSplitService(repository=PostgresBankTransactionSplitRepository(self.connection), relation_service=self.relations)

    @staticmethod
    def payload(version=0):
        return {"version": version, "parts": [
            {"category_code": "test_principal", "amount": "1000000.00"},
            {"category_code": "test_interest", "amount": "1497.22"},
        ]}

    def test_real_save_child_read_and_unchanged_source_facts(self):
        before = self.connection.fetch_one("SELECT to_jsonb(b) AS fact FROM app.bank_transactions b WHERE id=%s::uuid", (self.parent,))
        saved = self.service.save("txn-split-test", self.payload(), actor_id="tester")
        self.assertEqual(saved["version"], 1)
        self.assertTrue(saved["changed"])
        self.assertEqual(saved["affected_months"], ["2026-09"])
        interest = next(tag for tag in saved["tag_definitions"] if tag["code"] == "test_interest")
        self.assertEqual((interest["primary_label"], interest["sub_label"]), ("费用", "利息"))
        reloaded = self.service.read(saved["parts"][0]["id"])
        self.assertEqual(reloaded["parts"], saved["parts"])
        self.assertEqual(reloaded["canonical_transaction_id"], self.parent)
        rows = self.connection.fetch_all("SELECT id::text,amount,signed_amount,parent_row_id FROM app.bank_transaction_units ORDER BY amount DESC")
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["amount"] for row in rows), Decimal("1001497.22"))
        self.assertEqual(sum(row["signed_amount"] for row in rows), Decimal("-1001497.22"))
        self.assertEqual({row["parent_row_id"] for row in rows}, {"txn-split-test"})
        self.assertEqual(self.connection.fetch_one("SELECT to_jsonb(b) AS fact FROM app.bank_transactions b WHERE id=%s::uuid", (self.parent,)), before)
        with self.connection.transaction() as tx:
            tags = PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows(tx, settings=self.settings, transaction_ids=[part["id"] for part in saved["parts"]])
        self.assertEqual({row["effective_category_code"] for row in tags.values()}, {"test_principal", "test_interest"})

    def test_noop_conflict_and_explicit_clear(self):
        saved = self.service.save(self.parent, self.payload(), actor_id="tester")
        same = self.service.save(self.parent, {"version": 1, "parts": saved["parts"]}, actor_id="tester")
        self.assertFalse(same["changed"])
        self.assertEqual(same["version"], 1)
        with self.assertRaises(BankTransactionSplitError) as error:
            self.service.save(self.parent, self.payload(), actor_id="tester")
        self.assertEqual(error.exception.code, "split_version_conflict")
        cleared = self.service.save(self.parent, {"version": 1, "parts": [], "category_code": "test_interest"}, actor_id="tester")
        self.assertEqual(cleared["version"], 2)
        self.assertEqual(self.service.read(self.parent)["parts"], [])
        self.assertEqual(self.service.read(self.parent)["category_code"], "test_interest")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.bank_transaction_units")["n"], 1)

    def test_two_concurrent_writers_cannot_overwrite(self):
        def save():
            try:
                return self.service.save(self.parent, self.payload(), actor_id="tester")["version"]
            except BankTransactionSplitError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: save(), range(2)))
        self.assertCountEqual(results, [1, "split_version_conflict"])
        self.assertEqual(len(self.service.read(self.parent)["parts"]), 2)

    def test_relation_failure_rolls_back_items_and_audit(self):
        class FailedRelationOwner:
            def apply(self, *_args, **_kwargs):
                raise RuntimeError("test transaction failure")
        service = BankTransactionSplitService(repository=PostgresBankTransactionSplitRepository(self.connection), relation_service=FailedRelationOwner())
        with self.assertRaisesRegex(RuntimeError, "test transaction failure"):
            service.save(self.parent, self.payload(), actor_id="tester")
        self.assertEqual(self.service.read(self.parent)["version"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events WHERE event_type='bank_transaction_splits_saved'")["n"], 0)

    def test_batch_read_preserves_alias_order_and_unit_detail_preserves_parent(self):
        from fin_ops_platform.services.bank_transaction_unit import (
            bank_unit_display,
            bank_unit_matches_invoice,
            original_bank_transaction,
        )
        from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository

        saved = self.service.save(self.parent, self.payload(), actor_id="tester")
        child_ids = [part["id"] for part in saved["parts"]]
        rows = self.service.read_many({"transaction_ids": [child_ids[1], self.parent, child_ids[0]]})["rows"]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["transaction_id"] == "txn-split-test" and row["parts"] == saved["parts"] for row in rows))
        units = PostgresCoreRepository(self.connection).list_bank_transaction_units_by_ids(child_ids)
        self.assertEqual(sum(unit.amount for unit in units), Decimal("1001497.22"))
        self.assertEqual(sum(unit.amount for unit in units if bank_unit_matches_invoice(unit)), Decimal("1497.22"))
        for unit in units:
            self.assertEqual(original_bank_transaction(unit).amount, Decimal("1001497.22"))
            self.assertEqual(len(bank_unit_display(unit)["bank_split_parts"]), 2)

    def test_old_parent_tag_writer_cannot_override_child_tags(self):
        from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryValidationError
        from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
            PostgresBankTransactionCategoryRepository,
        )

        saved = self.service.save(self.parent, self.payload(), actor_id="tester")
        with self.assertRaises(BankTransactionCategoryValidationError) as error:
            with self.connection.transaction() as tx:
                PostgresBankTransactionCategoryRepository(tx).apply_mutation(
                    transaction=tx, transaction_id=self.parent, mutation_type="manual_assign",
                    record={"category_code": "test_interest"}, actor_id="tester", action="manual_assign", metadata={},
                )
        self.assertEqual(error.exception.error_code, "bank_transaction_is_split")
        self.assertEqual(self.service.read(self.parent)["parts"], saved["parts"])

    def test_written_off_bank_requires_reversal_and_selection_proof_uses_child(self):
        from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
            PostgresBankTransactionCategoryRepository,
        )
        self.connection.execute("UPDATE app.bank_transactions SET written_off_amount=1 WHERE id=%s::uuid", (self.parent,))
        with self.assertRaises(BankTransactionSplitError) as error:
            self.service.save(self.parent, self.payload(), actor_id="tester")
        self.assertEqual(error.exception.code, "bank_transaction_already_written_off")
        self.assertEqual(self.service.read(self.parent)["parts"], [])
        self.connection.execute("UPDATE app.bank_transactions SET written_off_amount=0 WHERE id=%s::uuid", (self.parent,))
        saved = self.service.save(self.parent, self.payload(), actor_id="tester")
        ids = [part["id"] for part in saved["parts"]]
        with self.connection.transaction() as tx:
            proofs = PostgresBankTransactionCategoryRepository(tx).turnover_bank_row_selection_proofs(ids, transaction=tx)
        self.assertEqual(set(proofs), set(ids))
        self.assertEqual({proof["category_code"] for proof in proofs.values()}, {"test_principal", "test_interest"})
        self.assertTrue(all(proof["category_version"] == 1 and proof["category_source"] == "bank_split" for proof in proofs.values()))

    def test_production_probe_always_rolls_back_test_owned_facts(self):
        from fin_ops_platform.tools.bank_transaction_split_smoke import run
        result = run(self.connection)
        self.assertTrue(result['rollback_verified'])
        self.assertEqual(result['samples'], 100)
        self.assertEqual(self.connection.fetch_one('SELECT count(*) AS n FROM app.bank_transactions')['n'], 1)
        self.assertEqual(self.service.read(self.parent)['version'], 0)
