from __future__ import annotations

import hashlib
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from fin_ops_platform.services.invoice_source_attribute_repair import build_source_attribute_repair_plan
from fin_ops_platform.services.postgres_repositories.invoice_source_attribute_repair import apply_updates
from fin_ops_platform.tools.invoice_source_attribute_repair import read_sources

NUMBER = "26532000000000000001"


def invoice(**attrs):
    return {
        "invoice_id": "invoice-1",
        "digital_invoice_no": NUMBER,
        "invoice_code": None,
        "invoice_no": NUMBER,
        "buyer_tax_no": "BUYER",
        "invoice_date": "2026-09-24",
        "updated_at": "2026-09-24T12:00:00",
        "source_links": [{"source_type": "manual_invoice_import", "batch_id": "batch-1"}],
        "raw_payload": {
            "normalized_payload": {
                "amount": "100",
                "tax_amount": "13",
                "total_with_tax": "113",
                "source_links": ["retained"],
                **attrs,
            }
        },
    }


def source(kind="电子发票（增值税专用发票）", **attrs):
    return {
        "file_id": "original-1",
        "sha256": "a" * 64,
        "source_kind": "invoice_export",
        "invoice_ids": ["invoice-1"],
        "rows": [
            {
                "digital_invoice_no": NUMBER,
                "buyer_tax_no": "BUYER",
                "invoice_date": "2026-09-24",
                "invoice_kind": kind,
                "source_row_number": 2,
                **attrs,
            }
        ],
    }


class SourceAttributeRepairTests(unittest.TestCase):
    def plan(self, originals, current=None):
        return build_source_attribute_repair_plan([current or invoice()], originals, [])

    def test_exact_original_type_preserves_finance_identity_and_evidence(self):
        current = invoice()
        original = deepcopy(current)
        plan = self.plan([source()], current)
        changed = plan["updates"][0]["raw_payload"]["normalized_payload"]
        self.assertEqual(changed["invoice_kind_code"], "vat_special")
        self.assertEqual(changed["invoice_kind"], "电子发票（增值税专用发票）")
        self.assertEqual(changed["invoice_kind_evidence"][0]["source_row_number"], 2)
        for name in ("amount", "tax_amount", "total_with_tax", "source_links"):
            self.assertEqual(changed[name], original["raw_payload"]["normalized_payload"][name])
        self.assertEqual(current, original)
        self.assertEqual(plan["rollback_manifest"]["invoices"], [current])

    def test_missing_unknown_unavailable_and_conflict_are_distinct(self):
        cases = [
            ([source(None)], "not_provided"),
            ([source("未收录的原始类型")], "unmapped"),
            ([], "source_unavailable"),
            ([source(), source("普通发票")], "conflict"),
            ([source(buyer_tax_no="OTHER")], "conflict"),
            ([source(invoice_date="2026-09-23")], "conflict"),
        ]
        for originals, status in cases:
            with self.subTest(status=status):
                data = self.plan(originals)["updates"][0]["raw_payload"]["normalized_payload"]
                self.assertEqual(data["invoice_kind_status"], status)
                self.assertIsNone(data["invoice_kind_code"])

    def test_equivalent_aliases_are_not_conflicts_and_repeat_is_noop(self):
        originals = [source(), source("增值税专用发票")]
        first = self.plan(originals)
        current = invoice()
        current["raw_payload"] = first["updates"][0]["raw_payload"]
        second = self.plan(originals, current)
        self.assertEqual(second["update_count"], 0)
        self.assertEqual(second["classification_counts"], {"confirmed": 1})

    def test_unrelated_source_and_weak_identity_cannot_supply_a_type(self):
        original = source()
        original["invoice_ids"] = ["other"]
        self.assertEqual(self.plan([original])["classification_counts"], {"source_unavailable": 1})
        original = source()
        original["rows"][0].update(digital_invoice_no=None, invoice_no=None, seller_tax_no="S", total_with_tax="113")
        current = invoice()
        current.update(digital_invoice_no=None, invoice_no=None, seller_tax_no="S", total_with_tax="113")
        self.assertEqual(self.plan([original], current)["classification_counts"], {"source_unavailable": 1})

    def test_reader_does_not_claim_coverage_when_file_lacks_exact_invoice(self):
        content = b"original bytes"
        store = Mock()
        store.read_import_file.return_value = content
        file = {
            "file_id": "file-1",
            "sha256": hashlib.sha256(content).hexdigest(),
            "original_filename": "original.pdf",
            "stored_file_path": "/registered/file",
            "raw_payload": {"normalized_payload": {"batch_type": "input_invoice", "batch_id": "batch-1"}},
        }
        current = invoice()
        current["source_links"].append({"source_attachment_key": "oa:exact"})
        with (
            patch("fin_ops_platform.tools.invoice_source_attribute_repair.load_original_files", return_value=[file]),
            patch("fin_ops_platform.tools.invoice_source_attribute_repair.load_etc_originals", return_value=[]),
            patch("fin_ops_platform.tools.invoice_source_attribute_repair.OAAttachmentInvoiceService") as parser,
            patch(
                "fin_ops_platform.tools.invoice_source_attribute_repair.load_original_invoice_attachments",
                return_value=[],
            ) as attachments,
        ):
            parser.return_value.parse_content_result.return_value = {"evidences": [{"digital_invoice_no": "different"}]}
            _, failures = read_sources(Mock(), [current], store)
        attachments.assert_called_once_with(unittest.mock.ANY, ["oa:exact"])
        self.assertIn({"file_id": "oa:exact", "reason": "registration_missing"}, failures)

    def test_repository_uses_version_check_and_refuses_partial_write(self):
        plan = self.plan([source()])
        connection = Mock()
        connection.execute.return_value = 1
        apply_updates(connection, plan["updates"])
        sql, params = connection.execute.call_args.args
        self.assertIn("updated_at=now()", sql)
        self.assertIn("raw_payload=%s and updated_at=%s", sql)
        self.assertEqual(params[1], "invoice-1")
        self.assertEqual(params[-1], "2026-09-24T12:00:00")
        empty = Mock()
        apply_updates(empty, [])
        empty.execute.assert_not_called()
        connection.execute.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "Concurrent"):
            apply_updates(connection, plan["updates"])

    def test_corrupt_registered_original_is_reported_and_never_used(self):
        file = {
            "file_id": "original-1",
            "sha256": "a" * 64,
            "original_filename": "original.pdf",
            "stored_file_path": "/registered/file",
            "raw_payload": {"normalized_payload": {"batch_type": "input_invoice", "batch_id": "batch-1"}},
        }
        store = Mock()
        store.read_import_file.return_value = b"changed original"
        with (
            patch("fin_ops_platform.tools.invoice_source_attribute_repair.load_original_files", return_value=[file]),
            patch("fin_ops_platform.tools.invoice_source_attribute_repair.load_etc_originals", return_value=[]),
            patch(
                "fin_ops_platform.tools.invoice_source_attribute_repair.load_original_invoice_attachments",
                return_value=[],
            ),
        ):
            sources, failures = read_sources(Mock(), [invoice()], store)
        self.assertEqual(sources, [])
        self.assertEqual(failures, [{"file_id": "original-1", "reason": "ValueError"}])
