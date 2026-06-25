from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.workbench_canonical_oa_attachment_raw_payload_repairer import (
    WorkbenchCanonicalOaAttachmentRawPayloadRepairer,
)


class WorkbenchCanonicalOaAttachmentRawPayloadRepairerTests(unittest.TestCase):
    def test_repair_appends_canonical_invoice_to_source_oa_section_and_refreshes_summary(self) -> None:
        calls: list[tuple[str, object]] = []
        invoice = SimpleNamespace(id="invoice-1")
        payload: dict[str, object] = {
            "paired": {"oa": [{"id": "oa-1"}], "bank": [], "invoice": []},
            "open": {"oa": [], "bank": [], "invoice": []},
        }
        repairer = WorkbenchCanonicalOaAttachmentRawPayloadRepairer(
            list_invoices=lambda: [invoice],
            source_link_for_invoice=lambda invoice, oa_row_ids: {"derived_from_oa_id": "oa-1"},
            source_oa_id_for_attachment_link=lambda source_link, oa_row_ids: "oa-1",
            canonical_oa_attachment_invoice_row=lambda invoice, **kwargs: {
                "id": invoice.id,
                "source": kwargs["source_link"]["derived_from_oa_id"],
            },
            replace_raw_workbench_row=lambda *args, **kwargs: False,
            dedupe_raw_workbench_rows_by_id=lambda payload, **kwargs: calls.append(("dedupe", kwargs)),
            refresh_raw_workbench_payload_summary=lambda payload: calls.append(("summary", payload)),
        )

        repairer.repair(payload)

        self.assertEqual(payload["paired"]["invoice"], [{"id": "invoice-1", "source": "oa-1"}])
        self.assertEqual([call[0] for call in calls], ["dedupe", "summary"])

    def test_repair_replaces_existing_invoice_without_appending_duplicate(self) -> None:
        calls: list[str] = []
        invoice = SimpleNamespace(id="invoice-1")
        payload: dict[str, object] = {
            "paired": {"oa": [{"id": "oa-1"}], "bank": [], "invoice": [{"id": "invoice-1", "stale": True}]},
            "open": {"oa": [], "bank": [], "invoice": []},
        }

        def replace(payload: dict[str, object], **kwargs: object) -> bool:
            calls.append("replace")
            payload["paired"]["invoice"][0] = kwargs["replacement"]
            return True

        repairer = WorkbenchCanonicalOaAttachmentRawPayloadRepairer(
            list_invoices=lambda: [invoice],
            source_link_for_invoice=lambda invoice, oa_row_ids: {"derived_from_oa_id": "oa-1"},
            source_oa_id_for_attachment_link=lambda source_link, oa_row_ids: "oa-1",
            canonical_oa_attachment_invoice_row=lambda invoice, **kwargs: {"id": invoice.id, "fresh": True},
            replace_raw_workbench_row=replace,
            dedupe_raw_workbench_rows_by_id=lambda payload, **kwargs: calls.append("dedupe"),
            refresh_raw_workbench_payload_summary=lambda payload: calls.append("summary"),
        )

        repairer.repair(payload)

        self.assertEqual(payload["paired"]["invoice"], [{"id": "invoice-1", "fresh": True}])
        self.assertEqual(calls, ["replace", "dedupe", "summary"])

    def test_repair_noops_when_payload_has_no_oa_rows(self) -> None:
        calls: list[str] = []
        repairer = WorkbenchCanonicalOaAttachmentRawPayloadRepairer(
            list_invoices=lambda: calls.append("list") or [SimpleNamespace(id="invoice-1")],
            source_link_for_invoice=lambda invoice, oa_row_ids: {},
            source_oa_id_for_attachment_link=lambda source_link, oa_row_ids: None,
            canonical_oa_attachment_invoice_row=lambda invoice, **kwargs: {},
            replace_raw_workbench_row=lambda *args, **kwargs: False,
            dedupe_raw_workbench_rows_by_id=lambda payload, **kwargs: calls.append("dedupe"),
            refresh_raw_workbench_payload_summary=lambda payload: calls.append("summary"),
        )

        repairer.repair({"paired": {"oa": [], "invoice": []}, "open": {"oa": [], "invoice": []}})

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
