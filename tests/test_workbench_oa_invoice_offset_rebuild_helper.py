from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_oa_invoice_offset_rebuild_helper import (
    WorkbenchOaInvoiceOffsetRebuildHelper,
)


def _matches_source_oa(row: dict[str, object], oa_row_id: object) -> bool:
    return str(row.get("source_oa_id") or "").strip() == str(oa_row_id or "").strip()


class WorkbenchOaInvoiceOffsetRebuildHelperTests(unittest.TestCase):
    def _helper(self, applicant_names: list[str] | None = None) -> WorkbenchOaInvoiceOffsetRebuildHelper:
        return WorkbenchOaInvoiceOffsetRebuildHelper(
            applicant_names_provider=lambda: applicant_names if applicant_names is not None else [" 周洁莹 "],
            attachment_matches_oa=_matches_source_oa,
            offset_tag="冲",
        )

    def test_cached_payload_does_not_need_rebuild_without_config_or_matching_attachment(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "oa_rows": [{"id": "oa-1", "applicant": "周洁莹"}],
                        "invoice_rows": [{"id": "inv-1", "source_kind": "manual", "source_oa_id": "oa-1"}],
                    }
                ]
            }
        }

        self.assertFalse(self._helper([]).cached_payload_needs_rebuild(payload))
        self.assertFalse(self._helper().cached_payload_needs_rebuild(payload))

    def test_open_group_with_configured_applicant_and_attachment_needs_rebuild(self) -> None:
        payload = {
            "open": {
                "groups": [
                    {
                        "oa_rows": [{"id": "oa-1", "applicant": "周洁莹"}],
                        "invoice_rows": [
                            {"id": "inv-1", "source_kind": "oa_attachment_invoice", "source_oa_id": "oa-1"}
                        ],
                    }
                ]
            }
        }

        self.assertTrue(self._helper().cached_payload_needs_rebuild(payload))

    def test_paired_group_needs_rebuild_when_offset_metadata_is_missing(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "oa_rows": [{"id": "oa-1", "applicant": "周洁莹", "tags": ["冲"], "cost_excluded": True}],
                        "invoice_rows": [
                            {
                                "id": "inv-1",
                                "source_kind": "oa_attachment_invoice",
                                "source_oa_id": "oa-1",
                                "tags": [],
                                "cost_excluded": True,
                            }
                        ],
                    }
                ]
            }
        }

        self.assertTrue(self._helper().cached_payload_needs_rebuild(payload))

    def test_paired_group_with_complete_offset_metadata_does_not_need_rebuild(self) -> None:
        payload = {
            "paired": {
                "groups": [
                    {
                        "oa_rows": [{"id": "oa-1", "applicant": "周洁莹", "tags": ["冲"], "cost_excluded": True}],
                        "invoice_rows": [
                            {
                                "id": "inv-1",
                                "source_kind": "oa_attachment_invoice",
                                "source_oa_id": "oa-1",
                                "tags": ["冲"],
                                "cost_excluded": True,
                            }
                        ],
                    }
                ]
            }
        }

        self.assertFalse(self._helper().cached_payload_needs_rebuild(payload))

    def test_attachment_invoice_rows_for_oa_only_returns_attachment_matches(self) -> None:
        rows = [
            {"id": "inv-1", "source_kind": "oa_attachment_invoice", "source_oa_id": "oa-1"},
            {"id": "inv-2", "source_kind": "oa_attachment_invoice", "source_oa_id": "oa-2"},
            {"id": "inv-3", "source_kind": "manual", "source_oa_id": "oa-1"},
        ]

        matches = self._helper().attachment_invoice_rows_for_oa({"id": "oa-1"}, rows)

        self.assertEqual([row["id"] for row in matches], ["inv-1"])


if __name__ == "__main__":
    unittest.main()
