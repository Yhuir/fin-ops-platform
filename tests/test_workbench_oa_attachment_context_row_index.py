from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_row_source_ids
from fin_ops_platform.services.workbench_oa_attachment_context_row_index import (
    WorkbenchOaAttachmentContextRowIndex,
)


class WorkbenchOaAttachmentContextRowIndexTests(unittest.TestCase):
    def _index(self) -> WorkbenchOaAttachmentContextRowIndex:
        return WorkbenchOaAttachmentContextRowIndex(
            attachment_parent_oa_id=lambda value: str(value).split(":")[0],
            attachment_matches_oa=lambda row, oa_id: str(row.get("source_oa_id") or "") == str(oa_id),
            attachment_row_id_matches_oa=lambda invoice_id, oa_id: str(invoice_id).startswith(f"att-{oa_id}-"),
            oa_source_ids=oa_row_source_ids,
        )

    def test_grouped_payload_rows_by_id_indexes_rows_from_paired_and_unpaired_groups(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "oa_rows": [{"id": "oa-1", "type": "oa"}],
                        "bank_rows": [{"id": "bk-1", "type": "bank"}],
                        "invoice_rows": [{"id": "", "type": "invoice"}, "bad"],
                    }
                ],
            },
            "unpaired": {
                "groups": [{"invoice_rows": [{"id": "inv-1", "type": "invoice"}]}],
            },
        }

        rows_by_id = self._index().grouped_payload_rows_by_id(payload)

        self.assertEqual(set(rows_by_id), {"oa-1", "bk-1", "inv-1"})
        self.assertEqual(rows_by_id["oa-1"]["type"], "oa")

    def test_attachment_row_ids_by_oa_id_matches_derived_parent_matcher_and_invoice_id_fallback(self) -> None:
        rows_by_id = {
            "oa-1": {"id": "oa-1", "type": "oa"},
            "oa-2": {"id": "oa-2", "type": "oa"},
            "oa-3": {"id": "oa-3", "type": "oa"},
            "oa-4": {"id": "oa-4", "type": "oa"},
            "inv-derived": {
                "id": "inv-derived",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-1",
            },
            "inv-parent": {
                "id": "inv-parent",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-2:file:1",
            },
            "inv-matcher": {
                "id": "inv-matcher",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "source_oa_id": "oa-3",
            },
            "att-oa-4-01": {
                "id": "att-oa-4-01",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
            },
            "manual": {
                "id": "manual",
                "type": "invoice",
                "source_kind": "manual",
                "derived_from_oa_id": "oa-1",
            },
        }

        attachment_rows = self._index().attachment_row_ids_by_oa_id(rows_by_id)

        self.assertEqual(attachment_rows["oa-1"], ["inv-derived"])
        self.assertEqual(attachment_rows["oa-2"], ["inv-parent"])
        self.assertEqual(attachment_rows["oa-3"], ["inv-matcher"])
        self.assertEqual(attachment_rows["oa-4"], ["att-oa-4-01"])
        self.assertNotIn("manual", {row_id for row_ids in attachment_rows.values() for row_id in row_ids})

    def test_attachment_row_ids_by_oa_id_matches_oa_source_aliases(self) -> None:
        rows_by_id = {
            "oa-exp-2156": {
                "id": "oa-exp-2156",
                "type": "oa",
                "detail_fields": {"Mongo文档ID": "69fab21659b12d7d42a50a45"},
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-exp-69fab21659b12d7d42a50a45:item:0:fb2a9c9fab23",
            },
        }

        attachment_rows = self._index().attachment_row_ids_by_oa_id(rows_by_id)

        self.assertEqual(attachment_rows, {"oa-exp-2156": ["invoice-1"]})

    def test_invoice_row_is_attachment_context_requires_invoice_type_and_source_kind(self) -> None:
        index = self._index()

        self.assertTrue(
            index.invoice_row_is_attachment_context({"type": "invoice", "source_kind": "oa_attachment_invoice"})
        )
        self.assertFalse(index.invoice_row_is_attachment_context({"type": "bank", "source_kind": "oa_attachment_invoice"}))
        self.assertFalse(index.invoice_row_is_attachment_context({"type": "invoice", "source_kind": "manual"}))

    def test_oa_id_from_attachment_invoice_id_prefers_longest_matching_oa_id(self) -> None:
        self.assertEqual(
            self._index().oa_id_from_attachment_invoice_id("att-oa-1-extra-01", ["oa-1", "oa-1-extra"]),
            "oa-1-extra",
        )


if __name__ == "__main__":
    unittest.main()
