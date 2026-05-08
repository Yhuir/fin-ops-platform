from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceStatus, InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.invoice_inventory_stats_service import InvoiceInventoryStatsService


class InvoiceInventoryStatsServiceTests(unittest.TestCase):
    def test_builds_inventory_stats_from_canonical_invoices_and_oa_snapshots(self) -> None:
        counterparty = Counterparty(
            id="cp_001",
            name="云南高速公路联网收费管理有限公司",
            normalized_name="云南高速公路联网收费管理有限公司",
            counterparty_type="vendor",
        )
        manual_invoice = self._invoice(
            "inv_manual_001",
            "MAN001",
            counterparty,
            source_links=[{"source_type": "manual_invoice_import", "batch_id": "batch_manual_001"}],
        )
        submitted_manual_etc_invoice = self._invoice(
            "inv_etc_merged_001",
            "ETC001",
            counterparty,
            tags=["ETC"],
            source_links=[
                {"source_type": "manual_invoice_import", "batch_id": "batch_manual_001"},
                {"source_type": "etc_invoice_import", "batch_id": "etc_import_batch_001"},
            ],
            workbench_visibility="hidden_after_etc_submission",
        )
        extra_etc_invoice = self._invoice(
            "inv_etc_only_001",
            "ETC002",
            counterparty,
            tags=["ETC"],
            source_links=[{"source_type": "etc_import", "batch_id": "etc_import_batch_001"}],
            workbench_visibility="hidden_after_etc_submission",
        )

        stats = InvoiceInventoryStatsService().build_stats(
            invoices=[manual_invoice, submitted_manual_etc_invoice, extra_etc_invoice],
            etc_summary_batch_count=1,
            workbench_snapshots=[
                {"id": "oa-invoice-001", "type": "invoice", "source_kind": "oa_attachment_invoice"},
                {"id": "manual-row-001", "type": "invoice", "source_kind": "manual_invoice"},
            ],
        )

        self.assertEqual(
            stats.to_payload(),
            {
                "system_total": 3,
                "manual_import_total": 2,
                "workbench_visible_total": 1,
                "hidden_submitted_etc_total": 1,
                "extra_etc_total": 1,
                "etc_summary_batch_count": 1,
                "oa_attachment_total": 1,
            },
        )

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        counterparty: Counterparty,
        *,
        tags: list[str] | None = None,
        source_links: list[dict[str, str]] | None = None,
        workbench_visibility: str = "visible",
    ) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=invoice_no,
            counterparty=counterparty,
            amount=Decimal("13.07"),
            signed_amount=Decimal("13.07"),
            invoice_date="2026-02-27",
            tags=list(tags or []),
            source_links=list(source_links or []),
            workbench_visibility=workbench_visibility,
            status=InvoiceStatus.PENDING,
        )


if __name__ == "__main__":
    unittest.main()
