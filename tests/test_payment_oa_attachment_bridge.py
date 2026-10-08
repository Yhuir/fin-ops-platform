from __future__ import annotations

import unittest

from fin_ops_platform.services.invoice_expense_item_link_repair_service import (
    build_oa_attachment_invoice_link_audit_plan,
)
from fin_ops_platform.services.oa_attachment_invoice_cache import (
    ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
    attachment_invoice_cache_parser_version,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    load_oa_attachment_invoice_link_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_identity_bridge import (
    reconcile_oa_attachment_cache_identity_sources,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)
from tests.test_oa_attachment_invoice_promotion_service import _invoice

OA_ID = "oa-pay-payment-1"
ATTACHMENT_KEY = "payment-1:invoice.pdf"
INVOICE_NO = "26532000000000000888"


def _evidence(**overrides):
    return {
        "digital_invoice_no": INVOICE_NO,
        "invoice_no": INVOICE_NO,
        "evidence_type": "tax_invoice",
        "document_kind": "digital_invoice",
        "issue_date": "2025-12-03",
        "amount": "100.00",
        "tax_amount": "6.00",
        "total_with_tax": "106.00",
        "source_oa_id": OA_ID,
        "source_attachment_key": ATTACHMENT_KEY,
        "source_attachment_name": "invoice.pdf",
        **overrides,
    }


class PaymentOAAttachmentCandidateTests(unittest.TestCase):
    def test_current_whole_oa_context_removes_stale_nested_item(self):
        rows = [{
            "cache_source_attachment_key": "payment-cache",
            "oa_row_id": OA_ID,
            "source_attachment_key": ATTACHMENT_KEY,
            "source_attachment_name": "invoice.pdf",
            "source_expense_item_id": None,
            "source_expense_row_index": None,
            "invoices": [_evidence(source_expense_item_id="old:item:1", source_expense_row_index="1")],
        }]
        candidate = OAAttachmentInvoicePromotionService.candidates_from_source_rows(rows)[0]
        self.assertNotIn("source_expense_item_id", candidate.attachment_invoice)
        self.assertNotIn("source_expense_row_index", candidate.attachment_invoice)
        self.assertEqual(candidate.attachment_invoice["source_oa_id"], OA_ID)
        self.assertTrue(candidate.source_workbench_row_id.startswith(f"oa-att-inv-{OA_ID}-"))


    def test_whole_oa_audit_does_not_repair_conflicting_payment_owners(self):
        links = [{"source_type": "oa_attachment_invoice", "source_attachment_key": f"key-{i}",
                  "derived_from_oa_id": f"oa-pay-{i}"} for i in range(2)]
        edges = [{"is_current_whole_oa_owner": True, "canonical_oa_row_id": f"oa-pay-{i}"}
                 for i in range(2)]
        plan = build_oa_attachment_invoice_link_audit_plan([{
            "invoice_id": "invoice-conflict", "workbench_visibility": "visible",
            "source_links": links, "attachment_edges": edges, "strong_candidates": [],
        }])
        self.assertEqual(plan["classification_counts"]["conflict"], 1)
        self.assertEqual(plan["update_count"], 0)


class PaymentOAAttachmentBridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        url = require_postgres_test_database_url()
        apply_test_migrations(url)
        truncate_test_database(url)
        self.connection = PostgresConnection(PostgresSettings(database_url=url, pool_enabled=False))
        self.repository = PostgresOAAttachmentInvoiceRepository(self.connection)
        self.cache = PostgresOpsTaxEtcRepository(self.connection)

    def tearDown(self):
        self.connection.close()

    def _cache(self, **overrides):
        evidence = _evidence(**overrides)
        self.cache.save_oa_attachment_invoice_cache_entry("payment-cache", {
            "parser_version": attachment_invoice_cache_parser_version(),
            "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
            "invoices": [evidence], "evidences": [evidence], "artifacts": [],
        })

    def _register(self, *, attachment=True, status="completed", source_oa_id=OA_ID,
                  key=ATTACHMENT_KEY, form_type="支付申请"):
        self.connection.execute(
            "insert into app.oa_applications(oa_source_id, form_id, row_id, form_type, status, scope_month) "
            "values (%s, 'payment-form', %s, %s, %s, '2025-12-01')",
            (OA_ID, OA_ID, form_type, status),
        )
        if attachment:
            self.connection.execute(
                "insert into app.oa_attachments(oa_application_id, oa_source_id, form_id, row_id, "
                "source_attachment_key, filename, normalized_payload) "
                "select id, oa_source_id, form_id, row_id, %s, 'invoice.pdf', "
                "jsonb_build_object('source_oa_id', %s::text, 'source_attachment_name', 'invoice.pdf') "
                "from app.oa_applications where row_id=%s",
                (key, source_oa_id, OA_ID),
            )

    def _bridge(self):
        return reconcile_oa_attachment_cache_identity_sources(self.connection, oa_row_ids=[OA_ID])

    def _rows(self):
        return self.repository.list_promotion_source_rows(oa_row_ids=[OA_ID], canonical_keys={INVOICE_NO})

    def test_preview_cache_cannot_reverse_link_formally_imported_invoice(self):
        self._cache()
        PostgresCoreRepository(self.connection).save_invoices([_invoice(_evidence())])
        result = OAAttachmentInvoicePromotionService(invoice_repository=self.repository).promote_confirmed_invoice_identity_keys(
            {INVOICE_NO}, configured_mode="create_missing",
            parser_version=attachment_invoice_cache_parser_version(),
            cache_schema_version=ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
        )
        self.assertEqual(result["summary"]["matched_identity_count"], 0)
        self.assertEqual(self._rows(), [])
        row = self.connection.fetch_one("select source_links from app.invoices")
        self.assertEqual(row["source_links"], [])

    def test_current_whole_oa_registration_bridges_and_preserves_null_item(self):
        self._cache()
        self._register()
        self._bridge()
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["oa_row_id"], OA_ID)
        self.assertIsNone(rows[0]["source_expense_item_id"])
        self.assertIsNone(rows[0]["source_expense_row_index"])
        self._bridge()
        self.assertEqual(self._rows(), rows)
        PostgresCoreRepository(self.connection).save_invoices([_invoice(_evidence())])
        result = OAAttachmentInvoicePromotionService(invoice_repository=self.repository).promote_confirmed_invoice_identity_keys(
            {INVOICE_NO}, configured_mode="create_missing",
            parser_version=attachment_invoice_cache_parser_version(),
            cache_schema_version=ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
        )
        self.assertEqual(result["summary"]["matched_identity_count"], 1)
        source_links = self.connection.fetch_one("select source_links from app.invoices")["source_links"]
        self.assertEqual(len(source_links), 1)
        self.assertEqual(source_links[0]["derived_from_oa_id"], OA_ID)
        self.assertEqual(source_links[0]["source_attachment_key"], ATTACHMENT_KEY)
        self.assertNotIn("source_expense_item_id", source_links[0])

    def test_oa_without_attachment_does_not_bridge(self):
        self._cache()
        self._register(attachment=False)
        self._bridge()
        self.assertEqual(self._rows(), [])

    def test_deleted_owner_does_not_bridge(self):
        self._cache()
        self._register(status="deleted")
        self._bridge()
        self.assertEqual(self._rows(), [])

    def test_wrong_parent_does_not_bridge(self):
        self._cache()
        self._register(source_oa_id="oa-pay-other")
        self._bridge()
        self.assertEqual(self._rows(), [])

    def test_same_filename_different_key_is_not_a_payment_match(self):
        self._cache()
        self._register(key="different-key")
        self._bridge()
        self.assertEqual(self._rows(), [])

    def test_wrong_payload_parent_cannot_be_promoted(self):
        self._cache(source_oa_id="oa-pay-other")
        self._register()
        self._bridge()
        self.assertEqual(self._rows(), [])

    def test_registration_rollback_leaves_preview_only(self):
        self._cache()
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.connection.transaction() as transaction:
                transaction.execute(
                    "insert into app.oa_applications(oa_source_id, form_id, row_id, form_type, status, scope_month) "
                    "values (%s, 'payment-form', %s, '支付申请', 'completed', '2025-12-01')", (OA_ID, OA_ID),
                )
                raise RuntimeError("rollback")
        self._bridge()
        self.assertEqual(self._rows(), [])
        self.assertIsNotNone(self.cache.load_oa_attachment_invoice_cache_entry("payment-cache"))

    def test_payment_audit_requires_exact_current_registered_owner(self):
        self._register()
        invoice = _invoice(_evidence())
        invoice.source_links = [{
            "source_type": "oa_attachment_invoice", "source_id": ATTACHMENT_KEY,
            "source_attachment_key": ATTACHMENT_KEY, "derived_from_oa_id": OA_ID,
        }]
        PostgresCoreRepository(self.connection).save_invoices([invoice])
        snapshot = load_oa_attachment_invoice_link_audit_snapshot(self.connection)
        self.assertTrue(snapshot[0]["attachment_edges"][0]["is_current_whole_oa_owner"])
        plan = build_oa_attachment_invoice_link_audit_plan(snapshot)
        self.assertEqual(plan["classification_counts"]["valid_attachment_owner"], 1)
        self.assertEqual(plan["update_count"], 0)
        self.connection.execute("delete from app.oa_attachments")
        plan = build_oa_attachment_invoice_link_audit_plan(load_oa_attachment_invoice_link_audit_snapshot(self.connection))
        self.assertEqual(plan["classification_counts"]["unresolved"], 1)
        self.assertEqual(plan["update_count"], 0)
