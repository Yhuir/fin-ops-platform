from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.workbench_oa_attachment_source_link_resolver import (
    WorkbenchOaAttachmentSourceLinkResolver,
)


class WorkbenchOaAttachmentSourceLinkResolverTests(unittest.TestCase):
    def test_source_link_for_invoice_normalizes_oa_attachment_link_and_fills_derived_id(self) -> None:
        invoice = SimpleNamespace(
            oa_form_id="oa-form-1",
            source_links=[
                {"source_type": "manual_invoice_import", "derived_from_oa_id": "ignored"},
                {
                    "source_type": "oa_attachment_invoice",
                    "source_workbench_row_id": "oa-att-inv-1",
                    "source_expense_item_id": "item-1",
                    "none_value": None,
                },
            ],
        )

        link = WorkbenchOaAttachmentSourceLinkResolver.source_link_for_invoice(invoice, {"oa-form-1"})

        self.assertIsNotNone(link)
        self.assertEqual(link["derived_from_oa_id"], "oa-form-1")
        self.assertEqual(link["source_workbench_row_id"], "oa-att-inv-1")
        self.assertNotIn("none_value", link)

    def test_source_link_for_invoice_returns_none_without_matching_source_link(self) -> None:
        invoice = SimpleNamespace(
            oa_form_id="oa-form-1",
            source_links=[{"source_type": "manual_invoice_import"}],
        )

        self.assertIsNone(
            WorkbenchOaAttachmentSourceLinkResolver.source_link_for_invoice(invoice, {"oa-form-1"})
        )

    def test_source_oa_id_for_attachment_link_matches_known_oa_ids(self) -> None:
        source_link = {
            "source_workbench_row_id": "oa-att-inv-oa-form-2-item-1",
            "derived_from_oa_id": "oa-form-2",
            "source_expense_item_id": "item-1",
        }

        self.assertEqual(
            WorkbenchOaAttachmentSourceLinkResolver.source_oa_id_for_attachment_link(
                source_link,
                {"oa-form-1", "oa-form-2"},
            ),
            "oa-form-2",
        )


if __name__ == "__main__":
    unittest.main()
