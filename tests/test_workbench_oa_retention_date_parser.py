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


if __name__ == "__main__":
    unittest.main()
