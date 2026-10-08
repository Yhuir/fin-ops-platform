import unittest

from fin_ops_platform.services.oa_attachment_summary import attachment_summary


class AttachmentSummaryTests(unittest.TestCase):
    def test_no_cache_is_unknown_not_recognized_zero_result(self):
        result = attachment_summary(file_count=2, artifacts=[], invoices=[])
        self.assertEqual(result["attachment_status"], "unparsed")
        self.assertEqual(result["pending_attachment_count"], 2)
        self.assertEqual(result["unrecognized_attachment_count"], 0)

    def test_duplicate_invoice_files_count_one_invoice_and_no_non_invoice_files(self):
        invoices = [{"invoice_no": "12345678901234567890", "source_attachment_key": key}
                    for key in ("a", "b")]
        artifacts = [{"source_attachment_key": key, "parse_status": "parsed", "has_invoice_evidence": "true"}
                     for key in ("a", "b")]
        for evidence in (invoices, invoices[:1]):
            result = attachment_summary(file_count=2, artifacts=artifacts, invoices=evidence)
            self.assertEqual(result["importable_invoice_count"], 1)
            self.assertEqual(result["unrecognized_attachment_count"], 0)
            self.assertEqual(result["attachment_status"], "ready")

    def test_one_file_can_contain_multiple_invoices(self):
        invoices = [{"invoice_no": str(12345678901234567890 + index), "source_attachment_key": "a"}
                    for index in (0, 1)]
        result = attachment_summary(file_count=1,
            artifacts=[{"source_attachment_key": "a", "parse_status": "parsed"}], invoices=invoices)
        self.assertEqual(result["attachment_file_count"], 1)
        self.assertEqual(result["importable_invoice_count"], 2)
        self.assertEqual(result["unrecognized_attachment_count"], 0)

    def test_partial_failure_pending_unsupported_and_non_invoice_are_distinct(self):
        artifacts = [{"source_attachment_key": str(index), "parse_status": status}
                     for index, status in enumerate(("stale", "parse_failed", "unsupported", "no_evidence"))]
        result = attachment_summary(file_count=5, artifacts=artifacts, invoices=[])
        self.assertEqual(result["attachment_status"], "partial")
        self.assertEqual(result["pending_attachment_count"], 2)
        self.assertEqual(result["failed_attachment_count"], 1)
        self.assertEqual(result["unsupported_attachment_count"], 1)
        self.assertEqual(result["unrecognized_attachment_count"], 1)

    def test_empty_and_all_failed(self):
        self.assertEqual(attachment_summary(file_count=0, artifacts=[], invoices=[])["attachment_status"], "ready")
        result = attachment_summary(file_count=1,
            artifacts=[{"source_attachment_key": "a", "parse_status": "download_failed"}], invoices=[])
        self.assertEqual(result["attachment_status"], "failed")
        self.assertEqual(result["pending_attachment_count"], 0)


if __name__ == "__main__":
    unittest.main()
