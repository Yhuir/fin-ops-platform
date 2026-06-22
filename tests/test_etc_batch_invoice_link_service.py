from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_batch_invoice_link_service import EtcBatchInvoiceLinkService


class _RecordingEtcBatchInvoiceLinkRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def upsert_etc_batch_invoice_link(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"id": "link-1", **kwargs}


class EtcBatchInvoiceLinkServiceTests(unittest.TestCase):
    def test_links_submitted_etc_invoice_to_canonical_invoice_with_strict_metadata(self) -> None:
        repository = _RecordingEtcBatchInvoiceLinkRepository()
        service = EtcBatchInvoiceLinkService(repository=repository)
        invoice = SimpleNamespace(
            id="invoice-legacy-id",
            invoice_no="26537912570200055449",
            digital_invoice_no="26537912570200055449",
            invoice_code=None,
            invoice_date="2026-02-28",
        )
        etc_invoice = SimpleNamespace(
            id="etc_invoice_0028",
            invoice_number="26537912570200055449",
            business_batch_id="etc_business_batch_hist_20260413_241125",
            current_batch_id="etc_business_batch_hist_20260413_241125",
        )

        link = service.link_submitted_invoice(
            invoice=invoice,
            etc_invoice=etc_invoice,
            link_source="formal_invoice_import",
            confidence="strict",
            raw_payload={"match": "submitted_etc_identity"},
        )

        self.assertEqual(link["id"], "link-1")
        self.assertEqual(len(repository.calls), 1)
        self.assertEqual(repository.calls[0]["invoice_id"], "invoice-legacy-id")
        self.assertEqual(repository.calls[0]["business_batch_id"], "etc_business_batch_hist_20260413_241125")
        self.assertEqual(repository.calls[0]["etc_invoice_id"], "etc_invoice_0028")
        self.assertEqual(repository.calls[0]["digital_invoice_no"], "26537912570200055449")
        self.assertEqual(repository.calls[0]["link_source"], "formal_invoice_import")
        self.assertEqual(repository.calls[0]["confidence"], "strict")

    def test_requires_business_batch_and_invoice_identity(self) -> None:
        service = EtcBatchInvoiceLinkService(repository=_RecordingEtcBatchInvoiceLinkRepository())

        with self.assertRaises(ValueError):
            service.link_submitted_invoice(
                invoice=SimpleNamespace(id="invoice-1", invoice_no="INV-1"),
                etc_invoice=SimpleNamespace(id="etc_invoice_1", invoice_number="INV-1"),
            )

        with self.assertRaises(ValueError):
            service.link_submitted_invoice(
                invoice=SimpleNamespace(id="invoice-1"),
                etc_invoice=SimpleNamespace(id="etc_invoice_1", business_batch_id="batch-1"),
            )


if __name__ == "__main__":
    unittest.main()
