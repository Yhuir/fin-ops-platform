from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.domain.enums import ImportDecision
from fin_ops_platform.services.bank_identity_repair_service import build_bank_identity_repair_plan
from fin_ops_platform.services.object_dedup_decision_service import ObjectDedupDecisionService
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_identity_repair import (
    apply_bank_identity_repair,
    load_bank_identity_repair_rows,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import _identity_matches
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.tools.audit_object_identity import _bank_identity_payload
from fin_ops_platform.tools.import_audit_repair_ops import main

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def sample():
    values = {"id": "bank-test", "account_no": "62220001", "trade_time": "2026-09-22 10:20:30",
              "txn_date": "2026-09-22", "txn_direction": "outflow", "amount": "12.30",
              "signed_amount": "-12.30", "balance": "200.00", "currency": "CNY",
              "counterparty_name_raw": "供应商", "bank_serial_no": "REF001", "status": "pending"}
    identity = FinancialObjectIdentityPolicy().identify_bank_transaction_mapping(values)
    values.update(source_unique_key=identity.canonical_key.rsplit(":", 1)[0].replace("bank-v3:", "bank-v2:", 1),
                  data_fingerprint=identity.suspected_key)
    return {**values, "id": "11111111-1111-1111-1111-111111111111", "transaction_id": values["id"],
            "updated_at": "2026-09-22T00:00:00+00:00", "raw_payload": {"normalized_payload": values}}


class BankIdentityRepairTests(unittest.TestCase):
    def test_exact_plan_only_changes_identity_and_does_not_mutate_input(self):
        row = sample()
        before = copy.deepcopy(row)
        plan = build_bank_identity_repair_plan([row])
        self.assertEqual(row, before)
        self.assertEqual(plan["planned_count"], 1)
        update = plan["updates"][0]
        after_payload = copy.deepcopy(update["after_payload"])
        after_payload["normalized_payload"]["source_unique_key"] = row["source_unique_key"]
        self.assertEqual(after_payload, row["raw_payload"])
        self.assertEqual(plan["rollback_manifest"]["updates"], plan["updates"])
        self.assertEqual(build_bank_identity_repair_plan([])["planned_count"], 0)

    def test_rejects_missing_drift_ambiguous_owner_and_unrelated_identity(self):
        mutations = [lambda r: r.update(data_fingerprint="wrong"),
                     lambda r: r.update(bank_serial_no="other"),
                     lambda r: r.update(raw_payload={}),
                     lambda r: r["raw_payload"]["normalized_payload"].update(amount="50"),
                     lambda r: r.update(source_unique_key="bank-v4:unrelated")]
        for mutate in mutations:
            row = sample()
            mutate(row)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                build_bank_identity_repair_plan([row], transaction_ids=["bank-test"])
        row = sample()
        with self.assertRaises(ValueError):
            build_bank_identity_repair_plan([row], transaction_ids=["missing"])
        other = {**copy.deepcopy(row), "id": "other", "transaction_id": "other"}
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            build_bank_identity_repair_plan([row, other])

    def test_repeat_explicit_targets_is_noop_and_historical_import_proof_survives(self):
        row = sample()
        historical = copy.deepcopy(row)
        update = build_bank_identity_repair_plan([row])["updates"][0]
        row.update(source_unique_key=update["after_key"], raw_payload=update["after_payload"])
        self.assertEqual(build_bank_identity_repair_plan([row], transaction_ids=["bank-test"])["planned_count"], 0)
        self.assertTrue(_identity_matches(historical, row))
        historical["data_fingerprint"] = "changed"
        self.assertFalse(_identity_matches(historical, row))

    def test_timezone_normalization_and_valid_position_identity_audit(self):
        row = sample()
        policy = FinancialObjectIdentityPolicy()
        expected = policy.identify_bank_transaction_mapping(row)
        for value in [datetime(2026, 9, 22, 2, 20, 30, tzinfo=UTC), "2026-09-22T02:20:30Z"]:
            with self.subTest(value=value):
                modified = {**row, "trade_time": value}
                self.assertEqual(policy.identify_bank_transaction_mapping(modified).canonical_key, expected.canonical_key)
                self.assertEqual(_bank_identity_payload(policy, modified)["policy_canonical_key"], expected.canonical_key)
        position = policy.identify_bank_transaction_position_mapping(row)
        row["source_unique_key"] = position.canonical_key
        self.assertEqual(_bank_identity_payload(policy, row)["policy_canonical_key"], position.canonical_key)

    def test_canonical_identity_does_not_read_stale_payload_key(self):
        row = sample()
        identity = FinancialObjectIdentityPolicy().identify_bank_transaction_mapping(row)
        row.update(source_unique_key=identity.canonical_key, legacy_id="bank-test")
        txn = PostgresCoreRepository(None)._transaction_from_row(row)
        self.assertEqual(txn.source_unique_key, identity.canonical_key)
        row.update(source_unique_key=None, data_fingerprint=None)
        txn = PostgresCoreRepository(None)._transaction_from_row(row)
        self.assertIsNone(txn.source_unique_key)
        self.assertIsNone(txn.data_fingerprint)

    def test_cli_rejects_unscoped_execute_and_mixed_mode_before_connection(self):
        for args in [["--execute", "--repair-bank-identities"],
                     ["--dry-run", "--repair-bank-identities", "--repair-bank-audit-contract"],
                     ["--dry-run", "--bank-transaction-id", "bank-test"]]:
            with self.subTest(args=args), self.assertRaises(SystemExit):
                main(args, stdout=io.StringIO())


class BankIdentityRepairPostgresTests(unittest.TestCase):
    def setUp(self):
        self.url = require_postgres_test_database_url()
        apply_test_migrations(self.url)
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        row = sample()
        self.connection.execute("""insert into app.bank_transactions
            (id,legacy_mongo_id,account_no,txn_direction,counterparty_name_raw,amount,signed_amount,
             trade_time,txn_date,txn_month,bank_serial_no,source_unique_key,data_fingerprint,balance,currency,status,raw_payload)
            values (%s::uuid,'bank-test',%s,'outflow',%s,12.30,-12.30,'2026-09-22 10:20:30+08',
                    '2026-09-22','2026-09-01','REF001',%s,%s,200,'CNY','pending',%s::jsonb)""",
            (row["id"], row["account_no"], row["counterparty_name_raw"], row["source_unique_key"],
             row["data_fingerprint"], json.dumps(row["raw_payload"])))

    def facts(self):
        return self.connection.fetch_one("select to_jsonb(t) as facts from app.bank_transactions t")["facts"]

    def plan(self):
        return build_bank_identity_repair_plan(load_bank_identity_repair_rows(self.connection))

    def test_migrate_reload_repeat_import_and_preserve_every_other_field(self):
        before = self.facts()
        plan = self.plan()
        with self.connection.transaction() as tx:
            self.assertEqual(apply_bank_identity_repair(tx, plan["updates"], operator_id="tester", reason="verified identity migration"), 1)
        after = self.facts()
        for key in before.keys() - {"source_unique_key", "raw_payload", "updated_at"}:
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["raw_payload"], plan["updates"][0]["after_payload"])
        self.assertEqual(self.plan()["planned_count"], 0)
        repository = PostgresCoreRepository(self.connection)
        decision = ObjectDedupDecisionService(object_identity_repository=repository).decide_bank_transaction_import(
            sample()["raw_payload"]["normalized_payload"])
        self.assertEqual(decision.decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(decision.linked_object_id, "bank-test")
        loaded = repository.find_bank_transaction_by_identity(canonical_key=after["source_unique_key"])
        self.assertEqual(loaded.source_unique_key, after["source_unique_key"])

    def test_cas_conflict_and_transaction_failure_leave_no_partial_write(self):
        plan = self.plan()
        before = self.facts()
        with self.assertRaisesRegex(RuntimeError, "audit failed"):
            with self.connection.transaction() as tx:
                apply_bank_identity_repair(tx, plan["updates"], operator_id="tester", reason="verified identity migration")
                raise RuntimeError("audit failed")
        self.assertEqual(self.facts(), before)
        partial = copy.deepcopy(plan["updates"])
        partial.append({**partial[0], "id": "22222222-2222-2222-2222-222222222222"})
        with self.assertRaisesRegex(RuntimeError, "changed"), self.connection.transaction() as tx:
            apply_bank_identity_repair(tx, partial, operator_id="tester", reason="verified migration")
        self.assertEqual(self.facts(), before)
        self.connection.execute("update app.bank_transactions set updated_at=now()")
        changed = self.facts()
        with self.assertRaisesRegex(RuntimeError, "changed"), self.connection.transaction() as tx:
            apply_bank_identity_repair(tx, plan["updates"], operator_id="tester", reason="verified identity migration")
        self.assertEqual(self.facts(), changed)

    def test_cli_private_artifact_audit_and_repeat_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            artifact = str(Path(directory) / "bank.json")
            env = {"FIN_OPS_POSTGRES_DATABASE_URL": self.url,
                   "FIN_OPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT": directory}
            with patch.dict(os.environ, env), patch(
                "fin_ops_platform.tools.import_audit_repair_ops._validate_private_rollback_manifest_path"
            ):
                stream = io.StringIO()
                main(["--repair-bank-identities", "--dry-run", "--rollback-manifest-path", artifact], stdout=stream)
                plan = json.loads(stream.getvalue())
                args = ["--repair-bank-identities", "--execute", "--bank-transaction-id", "bank-test",
                        "--expected-fingerprint", plan["source_fingerprint"], "--rollback-manifest-path", artifact,
                        "--operator-id", "test", "--reason", "proven legacy identity"]
                before = self.facts()
                with patch("fin_ops_platform.tools.import_audit_repair_ops.AuditTrailService.record_action",
                           side_effect=RuntimeError("audit unavailable")), self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                    main(args, stdout=io.StringIO())
                self.assertEqual(self.facts(), before)
                stream = io.StringIO()
                main(args, stdout=stream)
                self.assertEqual(json.loads(stream.getvalue())["updated_count"], 1)
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    main(args, stdout=io.StringIO())
                stream = io.StringIO()
                main(["--repair-bank-identities", "--dry-run", "--bank-transaction-id", "bank-test"], stdout=stream)
                self.assertEqual(json.loads(stream.getvalue())["planned_count"], 0)
                self.assertEqual(self.connection.fetch_one(
                    "select count(*) as n from audit.events where action='bank_identity_repair'")["n"], 1)
