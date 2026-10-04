from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import Mock

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import load_original_invoice_attachments

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def pending_item(key="pending-original"):
    return {
        "expense_item_id": "pending-oa:item:1",
        "attachment_files": [{"fileName": "original.pdf", "filePath": "/original.pdf"}],
        "attachment_artifacts": [{
            "source_attachment_key": key, "source_expense_item_id": "pending-oa:item:1",
            "attachment_name": "original.pdf", "source_attachment_name": "original.pdf",
            "file_path": "/original.pdf",
        }],
        # Extracted financial values must never supply original-file registration.
        "attachment_invoices": [{"source_attachment_key": "unregistered-cache-only", "amount": "999"}],
    }


class OriginalInvoiceAttachmentSourceTests(unittest.TestCase):
    def row(self):
        return {
            "source_attachment_key": "pending-original", "filename": "original.pdf",
            "normalized_payload": pending_item()["attachment_artifacts"][0],
            "source_owner_type": "pending_expense_item", "source_oa_id": "pending-oa",
            "source_expense_item_id": "pending-oa:item:1", "registered_file_count": 1,
        }

    def test_empty_scope_does_not_query(self):
        connection = Mock()
        self.assertEqual(load_original_invoice_attachments(connection, []), [])
        connection.fetch_all.assert_not_called()

    def test_duplicate_registered_owners_are_rejected_even_if_file_values_match(self):
        row = self.row()
        connection = Mock(fetch_all=Mock(return_value=[row, deepcopy(row)]))
        with self.assertRaisesRegex(ValueError, "ambiguous registered owners"):
            load_original_invoice_attachments(connection, ["pending-original"])

    def test_owner_and_exact_file_registration_are_required(self):
        for field, value in (("source_expense_item_id", "other-item"),
                             ("registered_file_count", 0), ("registered_file_count", 2)):
            with self.subTest(field=field, value=value):
                row = self.row()
                row[field] = value
                with self.assertRaisesRegex(ValueError, "pending item/file registration is inconsistent"):
                    load_original_invoice_attachments(Mock(fetch_all=Mock(return_value=[row])), ["pending-original"])

    def test_inconsistent_key_filename_or_missing_path_are_rejected(self):
        for field, value in (("source_attachment_key", "wrong-key"),
                             ("source_attachment_name", "other.pdf"), ("file_path", "")):
            with self.subTest(field=field):
                row = self.row()
                row["normalized_payload"][field] = value
                with self.assertRaises(ValueError):
                    load_original_invoice_attachments(Mock(fetch_all=Mock(return_value=[row])), ["pending-original"])


class OriginalInvoiceAttachmentSourcePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)

    def seed_pending(self, item=None, *, tenant="default", status="in_progress", oa_id="pending-oa"):
        payload = {"expense_items": [item or pending_item()]}
        self.connection.execute("""
            insert into app.oa_pending_payment_admissions
                (tenant_id, scope_key, oa_id, workflow_status, source_signature, source_payload)
            values (%s, '2026-09', %s, %s, 'source-registration', %s::jsonb)
        """, (tenant, oa_id, status, json.dumps(payload)))

    def seed_completed(self, key="completed-original"):
        self.connection.execute("""
            insert into app.oa_attachments
                (oa_source_id, row_id, source_attachment_key, filename, normalized_payload)
            values ('completed-oa', 'completed-oa:item:1', %s, 'completed.pdf', %s::jsonb)
        """, (key, json.dumps({"file_path": "/completed.pdf", "source_attachment_key": key,
                              "source_expense_item_id": "completed-oa:item:1"})))

    def test_reads_both_formal_owners_and_ignores_extracted_cache_values(self):
        self.seed_pending()
        self.seed_completed()
        with self.connection.transaction() as tx:
            tx.execute("set transaction read only")
            rows = load_original_invoice_attachments(tx, ["pending-original", "completed-original", "unregistered-cache-only"])
        self.assertEqual([row["source_attachment_key"] for row in rows], ["completed-original", "pending-original"])
        self.assertEqual([row["source_owner_type"] for row in rows], ["oa_attachment", "pending_expense_item"])
        self.assertEqual(rows[1]["source_oa_id"], "pending-oa")
        self.assertEqual(rows[1]["source_expense_item_id"], "pending-oa:item:1")
        self.assertEqual(rows[1]["normalized_payload"]["file_path"], "/original.pdf")
        self.assertNotIn("amount", rows[1]["normalized_payload"])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.oa_attachments")["n"], 1)

    def test_inactive_and_other_tenant_pending_registrations_do_not_resolve(self):
        self.seed_pending(status="completed")
        self.seed_pending(tenant="other", oa_id="other-oa")
        self.assertEqual(load_original_invoice_attachments(self.connection, ["pending-original"]), [])

    def test_pending_cross_item_file_or_duplicate_files_are_rejected(self):
        for change in ("owner", "path", "duplicate_file"):
            with self.subTest(change=change):
                self.connection.execute("delete from app.oa_pending_payment_admissions")
                item = pending_item()
                if change == "owner":
                    item["attachment_artifacts"][0]["source_expense_item_id"] = "other-item"
                elif change == "path":
                    item["attachment_files"][0]["filePath"] = "/other.pdf"
                else:
                    item["attachment_files"].append(dict(item["attachment_files"][0]))
                self.seed_pending(item)
                with self.assertRaisesRegex(ValueError, "pending item/file registration is inconsistent"):
                    load_original_invoice_attachments(self.connection, ["pending-original"])

    def test_duplicate_pending_artifacts_and_cross_owner_registrations_are_rejected(self):
        item = pending_item()
        item["attachment_artifacts"].append(dict(item["attachment_artifacts"][0]))
        self.seed_pending(item)
        with self.assertRaisesRegex(ValueError, "ambiguous registered owners"):
            load_original_invoice_attachments(self.connection, ["pending-original"])
        self.connection.execute("delete from app.oa_pending_payment_admissions")
        self.seed_pending()
        self.seed_completed("pending-original")
        with self.assertRaisesRegex(ValueError, "ambiguous registered owners"):
            load_original_invoice_attachments(self.connection, ["pending-original"])


if __name__ == "__main__":
    unittest.main()
