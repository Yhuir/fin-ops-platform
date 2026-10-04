from __future__ import annotations

import unittest
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace

from fin_ops_platform.domain.enums import BatchType, InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)

SOURCE_FIELDS = (
    "amount", "signed_amount", "tax_amount", "tax_amount_text", "total_with_tax", "tax_rate",
    "source_line_items", "source_line_count", "source_sheet_name", "source_sheet_role",
    "source_workbook_sha256", "financial_repair_source_file_id", "financial_repair_source_kind",
    "financial_repair_fingerprint", "invoice_header_repair_fingerprint", "source_batch_id",
)


def _original(*, number: str = "26532000000000000301", lines: list | None = None) -> Invoice:
    return Invoice(
        id=f"original-{number}", invoice_type=InvoiceType.INPUT, invoice_no=number,
        digital_invoice_no=number, source_unique_key=number,
        counterparty=Counterparty(id="source-seller", name="原件销方", normalized_name="原件销方", counterparty_type="vendor"),
        invoice_date="2026-09-03", amount=Decimal("-100.00"), signed_amount=Decimal("-100.00"),
        tax_amount=None, tax_amount_text="*", total_with_tax=None, tax_rate=None,
        source_line_items=deepcopy(lines or []), source_line_count=len(lines or []),
        source_sheet_name="发票基础信息", source_sheet_role="invoice_header",
        source_workbook_sha256="a" * 64, financial_repair_source_file_id="original-file",
        financial_repair_source_kind="invoice_export", financial_repair_fingerprint="repair-source-proof",
        invoice_header_repair_fingerprint="header-source-proof", source_batch_id="original-batch",
        source_links=[{"source_type": "manual_invoice_import", "source_id": number, "batch_id": "original-batch"}],
    )


def _attachment(number: str) -> dict:
    return {
        "evidence_type": "tax_invoice", "document_kind": "digital_invoice",
        "digital_invoice_no": number, "invoice_no": number, "invoice_type": "input",
        "issue_date": "2026-09-03", "seller_name": "OA销方", "seller_tax_no": "OA-TAX-ID",
        "buyer_name": "OA购方", "amount": "200.00", "net_amount": "200.00",
        "tax_amount": "26.00", "tax_amount_text": None, "total_with_tax": "226.00", "tax_rate": "13%",
        "source_line_items": [{"amount": "200.00", "tax_amount": "26.00", "tax_rate": "13%"}],
        "source_attachment_key": f"oa-source-{number}", "source_expense_item_id": f"oa-item-{number}",
        "source_expense_row_index": "1", "source_region_key": "document:1",
    }


def _financial_source(invoice: Invoice) -> dict:
    values = asdict(invoice)
    return {key: values[key] for key in SOURCE_FIELDS}


class InvoiceSourceMergeTests(unittest.TestCase):
    def test_existing_oa_link_preserves_original_nulls_empty_lines_and_provenance_idempotently(self):
        for owner in ("manual_invoice_import", "oa_attachment_invoice"):
            with self.subTest(owner=owner):
                original = _original()
                original.source_links = [{"source_type": owner, "source_id": "first-source"}]
                if owner == "oa_attachment_invoice":
                    original.tax_amount_text = None
                expected = _financial_source(original)
                service = ImportNormalizationService(existing_invoices=[original])
                for _ in range(2):
                    actual = service.upsert_oa_attachment_invoice(
                        _attachment(original.invoice_no), oa_form_id="oa-form", oa_row_id="oa-row",
                        source_workbench_row_id="oa-invoice", allow_create=True,
                    )
                    self.assertIs(actual, original)
                    self.assertEqual(_financial_source(actual), expected)
                    self.assertIsNone(actual.seller_name)
                    self.assertIsNone(actual.seller_tax_no)
                self.assertEqual(len(original.source_links), 1 if owner == "manual_invoice_import" else 2)
                self.assertEqual(original.oa_form_id, "oa-form")
                self.assertIn("OA附件", original.tags)

    def test_first_formal_original_replaces_source_provenance_as_one_group(self):
        original = _original(lines=[{"amount": "-100.00", "tax_rate": "13%"}])
        original.source_links = [{"source_type": "etc_invoice_import", "source_id": "etc-original"}]
        service = ImportNormalizationService(existing_invoices=[original])
        preview = service.preview_import(
            batch_type=BatchType.INPUT_INVOICE, source_name="new-original.xlsx", imported_by="finance",
            rows=[{"digital_invoice_no": original.invoice_no, "counterparty_name": "原件销方",
                   "invoice_date": "2026-09-03", "amount": "-100.00", "total_with_tax": "-100.00",
                   "source_sheet_name": "基础信息", "source_sheet_role": "invoice_header",
                   "source_line_count": 0, "source_line_items": []}],
        )
        service.confirm_import(preview.id)
        self.assertEqual(original.source_batch_id, preview.id)
        self.assertEqual(original.source_sheet_name, "基础信息")
        self.assertEqual(original.source_line_count, 0)
        self.assertEqual(original.source_line_items, [])
        self.assertEqual(original.amount, Decimal("-100.00"))
        for key in ("source_workbook_sha256", "financial_repair_source_file_id", "financial_repair_source_kind",
                    "financial_repair_fingerprint", "invoice_header_repair_fingerprint", "tax_rate", "tax_amount_text"):
            self.assertIsNone(getattr(original, key), key)


class InvoiceSourceRoundtripPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.core = PostgresCoreRepository(self.connection)

    def test_standard_save_roundtrip_preserves_full_original_financial_proof(self):
        for index, lines in enumerate(([], [{"amount": "-100.00", "tax_amount": "*", "tax_rate": "免税"}], [])):
            with self.subTest(lines=lines):
                original = _original(number=f"2653200000000000030{index}", lines=lines)
                if index == 2:
                    original.amount = original.signed_amount = None
                    original.total_with_tax = Decimal("100.00")
                expected = _financial_source(original)
                self.core.save_invoices([original])
                for _ in range(2):
                    loaded = self.core.list_invoices_by_ids([original.id])[0]
                    self.assertEqual(_financial_source(loaded), expected)
                    self.core.save_invoices([loaded])
                row = self.connection.fetch_one(
                    "select amount, signed_amount, tax_rate, tax_amount, total_with_tax, raw_payload from app.invoices where legacy_mongo_id=%s",
                    (original.id,),
                )
                self.assertIsNone(row["tax_rate"])
                self.assertIsNone(row["tax_amount"])
                self.assertEqual(row["amount"], expected["amount"])
                self.assertEqual(row["signed_amount"], expected["signed_amount"])
                self.assertEqual(row["total_with_tax"], expected["total_with_tax"])
                payload = row["raw_payload"]["normalized_payload"]
                for key in SOURCE_FIELDS[5:]:
                    self.assertEqual(payload[key], expected[key], key)

    def test_oa_repository_reloads_original_before_merge_and_preserves_nulls_and_empty_lines(self):
        original = _original()
        expected = _financial_source(original)
        self.core.save_invoices([original])
        incoming = asdict(original)
        incoming.update(
            amount="200.00", signed_amount="200.00", tax_amount="26.00", tax_amount_text="不征税",
            total_with_tax="226.00", tax_rate="13%", source_line_items=_attachment(original.invoice_no)["source_line_items"],
            source_line_count=1, source_sheet_name=None, source_workbook_sha256=None,
            financial_repair_source_file_id=None, source_batch_id="oa-batch", seller_name="OA销方",
            oa_form_id="oa-form", tags=["OA附件"],
            source_links=[{"source_type": "oa_attachment_invoice", "source_id": "oa-source",
                           "source_attachment_key": "oa-source", "derived_from_oa_id": "oa-row"}],
        )
        repository = PostgresOAAttachmentInvoiceRepository(self.connection)
        for _ in range(2):
            repository.save_invoices([incoming])
            actual = self.core.list_invoices_by_ids([original.id])[0]
            self.assertEqual(_financial_source(actual), expected)
            self.assertIsNone(actual.seller_name)
            self.assertEqual(len(actual.source_links), 1)
            self.assertEqual(actual.oa_form_id, "oa-form")
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.invoices")["n"], 1)

    def test_new_oa_promotion_keeps_parser_group_and_repeat_sync_is_idempotent(self):
        evidence = _attachment("26532000000000000309")
        repository = PostgresOAAttachmentInvoiceRepository(self.connection)
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository, promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
        )
        record = SimpleNamespace(id="oa-row", month="2026-09", attachment_invoices=[evidence])
        first = service.promote_records([record], ensure_matching=False)
        second = service.promote_records([record], ensure_matching=False)
        self.assertEqual(first["summary"]["created_invoice_count"], 1)
        self.assertEqual(second["summary"]["affected_invoice_count"], 0)
        rows = self.connection.fetch_all("select legacy_mongo_id from app.invoices")
        self.assertEqual(len(rows), 1)
        actual = self.core.list_invoices_by_ids([rows[0]["legacy_mongo_id"]])[0]
        self.assertEqual(actual.amount, Decimal("200.00"))
        self.assertEqual(actual.tax_amount, Decimal("26.00"))
        self.assertIsNone(actual.tax_amount_text)
        self.assertEqual(actual.total_with_tax, Decimal("226.00"))
        self.assertEqual(actual.tax_rate, "13%")
        self.assertEqual(actual.source_line_count, 1)
        self.assertEqual(actual.source_line_items[0]["tax_rate"], "13%")
        self.assertEqual(len(actual.source_links), 1)
