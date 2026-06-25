from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_oa_raw_payload_signal_month_helper import (
    WorkbenchOaRawPayloadSignalMonthHelper,
)


class WorkbenchOaRawPayloadSignalMonthHelperTests(unittest.TestCase):
    def test_months_from_raw_payload_collects_months_from_oa_rows(self) -> None:
        helper = WorkbenchOaRawPayloadSignalMonthHelper(
            is_month_prefix=lambda value: len(value) == 7 and value[4] == "-",
        )
        payload = {
            "paired": {
                "oa": [
                    {"id": "oa-1", "month": "2026-01"},
                    {"id": "oa-2", "detail_fields": {"申请日期": "2026-02-03"}},
                ],
            },
            "open": {
                "oa": [
                    {"id": "oa-3", "summary_fields": {"审批完成时间": "2026-03-04"}},
                    {"id": "oa-bad", "application_date": "bad"},
                ],
            },
        }

        self.assertEqual(helper.months_from_raw_payload(payload), {"2026-01", "2026-02", "2026-03"})

    def test_has_oa_attachment_invoice_signal_detects_tags_and_fields(self) -> None:
        self.assertTrue(
            WorkbenchOaRawPayloadSignalMonthHelper.has_oa_attachment_invoice_signal(
                {"paired": {"oa": [{"tags": ["OA附件"]}]}, "open": {"oa": []}}
            )
        )
        self.assertTrue(
            WorkbenchOaRawPayloadSignalMonthHelper.has_oa_attachment_invoice_signal(
                {"paired": {"oa": [{"detail_fields": {"附件发票数量": "1"}}]}, "open": {"oa": []}}
            )
        )
        self.assertFalse(
            WorkbenchOaRawPayloadSignalMonthHelper.has_oa_attachment_invoice_signal(
                {"paired": {"oa": [{"detail_fields": {"附件发票数量": "0 张"}}]}, "open": {"oa": []}}
            )
        )

    def test_first_month_from_oa_row_uses_first_parseable_candidate(self) -> None:
        helper = WorkbenchOaRawPayloadSignalMonthHelper(
            is_month_prefix=lambda value: value in {"2026-04"},
        )

        month = helper.first_month_from_oa_row(
            {
                "application_date": "bad",
                "apply_date": "2026-04-05",
                "summary_fields": {"申请日期": "2026-05-01"},
            }
        )

        self.assertEqual(month, "2026-04")


if __name__ == "__main__":
    unittest.main()
