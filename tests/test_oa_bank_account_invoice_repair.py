from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.import_audit_repair_service import build_oa_bank_account_invoice_repair_plan
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_oa_bank_account_invoice_repair,
    load_oa_bank_account_invoice_repair_snapshot,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def invoice(invoice_id, number):
    return {"id": "11111111-1111-1111-1111-111111111111" if invoice_id == "bad" else "22222222-2222-2222-2222-222222222222",
            "invoice_id": invoice_id, "invoice_type": "input", "invoice_no": number, "invoice_date": "2026-08-10",
            "amount": "175.47", "tax_amount": "10.53", "total_with_tax": "186.00",
            "status": "pending", "written_off_amount": "0", "source_batch_id": None, "etc_invoice_id": None,
            "source_links": [{"source_type": "oa_attachment_invoice", "source_attachment_key": "attachment"}]}


def facts():
    return {"invoice_id": "bad", "replacement_id": "good", "attachment_key": "attachment",
            "bank_account_numbers": {"53001905038050548106"}, "source_sha256": "verified-pdf-sha",
            "verified_invoices": [{"invoice_no": "26317000002920092512", "issue_date": "2026-08-10",
                                   "net_amount": "175.47", "tax_amount": "10.53", "total_with_tax": "186.00"}]}


class OABankAccountInvoiceRepairTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"invoices": [invoice("bad", "53001905038050548106"), invoice("good", "26317000002920092512")],
                         "attachments": [], "relations": [], "caches": [{"source_attachment_key": "cache"}], "references": {"relation": 0}}

    def test_exact_evidence_preserves_replacement_and_includes_recovery_data(self):
        plan = build_oa_bank_account_invoice_repair_plan(self.snapshot, **facts())
        self.assertEqual(plan["invoice_id"], "bad")
        self.assertEqual(plan["replacement_id"], "good")
        self.assertEqual(plan["invalidate_cache_keys"], ["cache"])
        self.assertEqual(plan["rollback_manifest"]["snapshot"], self.snapshot)

    def test_refuses_uncertain_identity_other_sources_used_invoice_and_downstream_references(self):
        mutations = [
            lambda s: s["references"].update(relation=1),
            lambda s: s["invoices"][0].update(written_off_amount="1"),
            lambda s: s["invoices"][0].update(status="reconciled"),
            lambda s: s["invoices"][0]["source_links"].append({"source_type": "manual_invoice_import"}),
            lambda s: s["invoices"][1].update(amount="176"),
            lambda s: s["invoices"][1].update(source_links=[]),
            lambda s: s["invoices"].pop(),
        ]
        for mutation in mutations:
            snapshot = copy.deepcopy(self.snapshot)
            mutation(snapshot)
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                build_oa_bank_account_invoice_repair_plan(snapshot, **facts())
        for change in [{"bank_account_numbers": set()}, {"verified_invoices": []}]:
            with self.assertRaises(ValueError):
                build_oa_bank_account_invoice_repair_plan(self.snapshot, **(facts() | change))


class OABankAccountInvoiceRepairPostgresTests(unittest.TestCase):
    def setUp(self):
        url = require_postgres_test_database_url()
        apply_test_migrations(url)
        truncate_test_database(url)
        self.connection = PostgresConnection(PostgresSettings(database_url=url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        for row in [invoice("bad", "53001905038050548106"), invoice("good", "26317000002920092512")]:
            self.connection.execute("""
                insert into app.invoices (id,legacy_mongo_id,invoice_type,invoice_no,digital_invoice_no,
                    invoice_date,invoice_month,amount,signed_amount,tax_amount,total_with_tax,status,source_links)
                values (%s::uuid,%s,'input',%s,%s,'2026-08-10','2026-08-01',175.47,175.47,10.53,186,'pending',%s::jsonb)
            """, (row["id"], row["invoice_id"], row["invoice_no"], row["invoice_no"], json.dumps(row["source_links"])))

        from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
        relation = {"case_id": "CASE-REPAIR", "relation_mode": "manual_confirmed", "status": "active", "version": 1,
                    "month_scope": "2026-08", "row_ids": ["oa-1", "good", "bad"], "row_types": ["oa", "invoice", "invoice"],
                    "special_metadata": {"formal_relation": {"origin": "system_deterministic"},
                                         "oa_attachment_bindings": [{"parent_oa_row_id": "oa-1", "invoice_row_ids": ["good", "bad"]}]}}
        PostgresWorkbenchRelationRepository(self.connection).save_workbench_pair_relation_delta(
            {"pair_relations": {"CASE-REPAIR": relation}}, changed_case_ids=["CASE-REPAIR"])

    def load_plan(self, tx):
        snapshot = load_oa_bank_account_invoice_repair_snapshot(
            tx, invoice_id="bad", replacement_id="good", attachment_key="attachment")
        return build_oa_bank_account_invoice_repair_plan(snapshot, **facts())

    def test_delete_and_matching_dirty_are_atomic_and_second_execution_cannot_delete_replacement(self):
        with self.assertRaisesRegex(RuntimeError, "queue failed"):
            with self.connection.transaction() as tx, patch(
                "fin_ops_platform.services.postgres_repositories.workbench_matching_queue."
                "PostgresWorkbenchMatchingQueueRepository.mark_workbench_matching_dirty_scopes_in_transaction",
                side_effect=RuntimeError("queue failed"),
            ):
                apply_oa_bank_account_invoice_repair(tx, self.load_plan(tx), operator_id="tester", reason="verified bank account misparse")
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.invoices")["n"], 2)
        with self.connection.transaction() as tx:
            result = apply_oa_bank_account_invoice_repair(tx, self.load_plan(tx), operator_id="tester", reason="verified bank account misparse")
        self.assertEqual(result["removed_invoice_count"], 1)
        self.assertEqual(result["repaired_relation_count"], 1)
        relation = self.connection.fetch_one("select row_ids,version,special_metadata from app.workbench_pair_relations where case_id='CASE-REPAIR'")
        self.assertEqual(relation["row_ids"], ["oa-1", "good"])
        self.assertEqual(relation["version"], 2)
        self.assertEqual(relation["special_metadata"]["oa_attachment_bindings"][0]["invoice_row_ids"], ["good"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.workbench_pair_relation_history where event_type='repair_false_invoice_member'")["n"], 1)
        self.assertEqual(self.connection.fetch_one("select legacy_mongo_id from app.invoices")["legacy_mongo_id"], "good")
        with self.assertRaises(ValueError):
            self.load_plan(self.connection)
