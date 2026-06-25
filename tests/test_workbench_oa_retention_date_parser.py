from __future__ import annotations

import unittest
from datetime import datetime

from fin_ops_platform.services.workbench_oa_retention_date_parser import WorkbenchOaRetentionDateParser


class WorkbenchOaRetentionDateParserTests(unittest.TestCase):
    def test_parse_accepts_iso_date_prefix_and_rejects_invalid_values(self) -> None:
        self.assertEqual(WorkbenchOaRetentionDateParser.parse("2026-03-01 12:34:56"), datetime(2026, 3, 1))
        self.assertIsNone(WorkbenchOaRetentionDateParser.parse(None))
        self.assertIsNone(WorkbenchOaRetentionDateParser.parse(""))
        self.assertIsNone(WorkbenchOaRetentionDateParser.parse("2026-3-1"))
        self.assertIsNone(WorkbenchOaRetentionDateParser.parse("2026-99-99"))

    def test_row_date_candidates_reads_oa_and_bank_fields(self) -> None:
        oa_candidates = WorkbenchOaRetentionDateParser.row_date_candidates(
            {
                "application_date": "2026-01-01",
                "apply_date": "2026-01-02",
                "summary_fields": {"申请日期": "2026-01-03", "ignored": "x"},
                "detail_fields": {"审批完成时间": "2026-01-04"},
            },
            row_type="oa",
        )
        bank_candidates = WorkbenchOaRetentionDateParser.row_date_candidates(
            {
                "trade_time": "2026-02-01 09:00:00",
                "pay_receive_time": "2026-02-02 09:00:00",
                "txn_date": "2026-02-03",
                "summary_fields": {"交易时间": "2026-02-04"},
                "detail_fields": {"记账日期": "2026-02-05"},
            },
            row_type="bank",
        )

        self.assertIn("2026-01-01", oa_candidates)
        self.assertIn("2026-01-04", oa_candidates)
        self.assertIn("2026-02-01 09:00:00", bank_candidates)
        self.assertIn("2026-02-05", bank_candidates)

    def test_row_predicates_use_parseable_candidates(self) -> None:
        row = {
            "application_date": "not-a-date",
            "summary_fields": {"申请日期": "2026-03-02"},
        }

        self.assertTrue(
            WorkbenchOaRetentionDateParser.row_is_on_or_after(
                row,
                datetime(2026, 3, 1),
                row_type="oa",
            )
        )
        self.assertTrue(WorkbenchOaRetentionDateParser.row_has_parseable_retention_date(row, row_type="oa"))
        self.assertFalse(
            WorkbenchOaRetentionDateParser.row_is_on_or_after(
                row,
                datetime(2026, 4, 1),
                row_type="oa",
            )
        )


if __name__ == "__main__":
    unittest.main()
