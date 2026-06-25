from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_supplemental_retained_oa_row_selector import (
    WorkbenchSupplementalRetainedOaRowSelector,
)


class WorkbenchSupplementalRetainedOaRowSelectorTests(unittest.TestCase):
    def test_selects_manual_and_bank_linked_oa_rows_after_cutoff(self) -> None:
        class RelationPort:
            def list_active_relations(self) -> list[dict[str, object]]:
                return [
                    {"row_ids": ["oa-old", "bank-new"], "row_types": ["oa", "bank"]},
                    {"row_ids": ["oa-stale", "bank-old"], "row_types": ["oa", "bank"]},
                ]

        selector = WorkbenchSupplementalRetainedOaRowSelector(
            manual_retained_oa_row_ids=lambda: ["oa-manual"],
            relation_read_port=RelationPort(),
            resolve_live_rows=lambda row_ids: [{"id": row_ids[0], "keep": row_ids[0] == "bank-new"}],
            row_is_on_or_after=lambda row, _cutoff, **_kwargs: bool(row.get("keep")),
        )

        self.assertEqual(selector.select(object()), ["oa-manual", "oa-old"])

    def test_skips_relation_when_live_bank_rows_are_missing(self) -> None:
        class RelationPort:
            def list_active_relations(self) -> list[dict[str, object]]:
                return [{"row_ids": ["oa-old", "bank-missing"], "row_types": ["oa", "bank"]}]

        selector = WorkbenchSupplementalRetainedOaRowSelector(
            manual_retained_oa_row_ids=lambda: ["oa-manual"],
            relation_read_port=RelationPort(),
            resolve_live_rows=lambda _row_ids: (_ for _ in ()).throw(KeyError("missing")),
            row_is_on_or_after=lambda *_args, **_kwargs: True,
        )

        self.assertEqual(selector.select(object()), ["oa-manual"])

    def test_missing_relation_port_returns_manual_rows_only(self) -> None:
        selector = WorkbenchSupplementalRetainedOaRowSelector(
            manual_retained_oa_row_ids=lambda: ["oa-manual"],
            relation_read_port=object(),
            resolve_live_rows=lambda _row_ids: [],
            row_is_on_or_after=lambda *_args, **_kwargs: False,
        )

        self.assertEqual(selector.select(object()), ["oa-manual"])


if __name__ == "__main__":
    unittest.main()
