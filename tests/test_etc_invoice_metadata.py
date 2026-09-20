from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.import_audit_repair_service import build_etc_invoice_payload_repair_plan
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.tools import import_audit_repair_ops as ops


def formal_invoice():
    return Invoice(
        id="formal-1",
        invoice_type=InvoiceType.INPUT,
        invoice_no="26537912210800169389",
        digital_invoice_no="26537912210800169389",
        source_unique_key="26537912210800169389",
        counterparty=Counterparty(id="vendor", name="正式销方", normalized_name="正式销方", counterparty_type="vendor"),
        amount=Decimal("33.55"),
        signed_amount=Decimal("33.55"),
        tax_amount=Decimal("1.01"),
        total_with_tax=Decimal("34.56"),
        tax_rate=None,
        invoice_date="2026-08-06",
        source_batch_id="manual-batch",
        tags=["人工导入"],
        source_links=[{"source_type": "manual_invoice_import", "source_id": "source", "batch_id": "manual-batch"}],
    )


def etc_invoice():
    return SimpleNamespace(
        id="etc-1",
        invoice_number="26537912210800169389",
        issue_date="2026-08-06",
        seller_name="ETC 销方",
        buyer_name="ETC 购方",
        tax_rate="0.03",
        amount_without_tax=Decimal("33.55"),
        total_amount=Decimal("34.56"),
        tax_amount=Decimal("1.01"),
        status="submitted",
        import_batch_id="etc-import",
        current_batch_id="etc-batch",
        last_batch_id="etc-batch",
    )


class EtcInvoiceMetadataTests(unittest.TestCase):
    def test_link_keeps_formal_facts_and_replays_without_writes(self):
        invoice = formal_invoice()
        service = ImportNormalizationService(existing_invoices=[invoice])
        persist = Mock()
        link = EtcExistingInvoiceLinkService(import_service=service, persist_linked_invoices=persist)
        self.assertEqual(link.link_etc_invoices_to_existing_invoices([etc_invoice()]), ["2026-08"])
        self.assertIsNone(invoice.tax_rate)
        self.assertIsNone(invoice.buyer_name)
        self.assertEqual(invoice.source_batch_id, "manual-batch")
        self.assertEqual(invoice.total_with_tax, Decimal("34.56"))
        self.assertEqual(invoice.etc_invoice_id, "etc-1")
        self.assertEqual(len(invoice.source_links), 2)
        self.assertEqual(link.link_etc_invoices_to_existing_invoices([etc_invoice()]), [])
        persist.assert_called_once()

    def test_failed_persistence_restores_metadata_for_retry(self):
        invoice = formal_invoice()
        before = deepcopy(invoice)
        persist = Mock(side_effect=[RuntimeError("write failed"), None])
        link = EtcExistingInvoiceLinkService(
            import_service=ImportNormalizationService(existing_invoices=[invoice]), persist_linked_invoices=persist
        )
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            link.link_etc_invoices_to_existing_invoices([etc_invoice()])
        self.assertEqual(invoice, before)
        self.assertEqual(link.link_etc_invoices_to_existing_invoices([etc_invoice()]), ["2026-08"])
        self.assertEqual(persist.call_count, 2)

    def test_repair_requires_original_empty_rate_and_preserves_etc_evidence(self):
        row = {
            "invoice_id": "formal-1",
            "invoice_no": "123",
            "tax_rate": None,
            "etc_tax_rate": "0.03",
            "raw_payload": {"normalized_payload": {"tax_rate": "0.03", "amount": "33.55"}},
            "import_rows": [{"normalized_payload": {"normalized_row": {"tax_rate": None}}}],
        }
        original = deepcopy(row)
        plan = build_etc_invoice_payload_repair_plan([row])
        self.assertEqual(len(plan["updates"]), 1)
        self.assertIsNone(plan["updates"][0]["after_tax_rate"])
        self.assertEqual(row, original)
        row["import_rows"][0]["normalized_payload"]["normalized_row"]["tax_rate"] = "0.03"
        self.assertEqual(build_etc_invoice_payload_repair_plan([row])["unresolved_invoice_ids"], ["formal-1"])
        row["raw_payload"]["normalized_payload"]["tax_rate"] = None
        self.assertEqual(build_etc_invoice_payload_repair_plan([row])["updates"], [])
        self.assertEqual(build_etc_invoice_payload_repair_plan([])["updates"], [])


class EtcInvoicePayloadRepairCliTests(unittest.TestCase):
    def test_preview_execute_and_drift_rejection(self):
        row = {
            "invoice_id": "formal-1",
            "invoice_no": "123",
            "tax_rate": None,
            "etc_tax_rate": "0.03",
            "raw_payload": {"normalized_payload": {"tax_rate": "0.03"}},
            "import_rows": [{"normalized_payload": {"normalized_row": {"tax_rate": None}}}],
        }
        connection = Mock()

        @contextmanager
        def transaction():
            yield connection

        connection.transaction = transaction
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"FIN_OPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT": directory}),
            patch.object(ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(ops, "PostgresConnection", return_value=connection),
            patch.object(ops, "load_etc_invoice_payload_repair_snapshot", return_value=[row]) as snapshot,
            patch.object(ops.PostgresCoreRepository, "repair_etc_invoice_payload", return_value=1) as repair,
            patch.object(ops.AuditTrailService, "record_action") as audit,
        ):
            path = os.path.join(directory, "rollback.json")
            scope = ["--repair-etc-invoice-payload", "--invoice-id", "formal-1", "--rollback-manifest-path", path]
            output = io.StringIO()
            self.assertEqual(ops.main(["--dry-run", *scope], stdout=output), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["planned_invoice_count"], 1)
            self.assertFalse(report["written"])
            self.assertNotIn("before_payload", output.getvalue())
            repair.assert_not_called()
            execute = [
                "--execute",
                *scope,
                "--expected-fingerprint",
                report["source_fingerprint"],
                "--operator-id",
                "operator",
                "--reason",
                "Repair confirmed ETC metadata pollution",
            ]
            output = io.StringIO()
            self.assertEqual(ops.main(execute, stdout=output), 0)
            self.assertEqual(json.loads(output.getvalue())["updated_invoice_count"], 1)
            audit.assert_called_once()
            self.assertEqual(repair.call_count, 1)
            changed = deepcopy(row)
            changed["etc_tax_rate"] = "0.06"
            snapshot.return_value = [changed]
            with self.assertRaisesRegex(RuntimeError, "unresolved or changed"):
                ops.main(execute, stdout=io.StringIO())
            self.assertEqual(repair.call_count, 1)
            self.assertEqual(connection.close.call_count, 3)

    def test_execute_requires_explicit_scope_and_rejects_mixed_modes(self):
        for args in (
            ["--execute", "--repair-etc-invoice-payload"],
            ["--dry-run", "--repair-etc-invoice-payload", "--batch-id", "bank-batch"],
        ):
            with self.subTest(args=args), patch.object(ops, "PostgresConnection") as connection:
                with self.assertRaises(SystemExit):
                    ops.main(args, stdout=io.StringIO())
                connection.assert_not_called()
