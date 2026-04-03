import unittest

from fin_ops_platform.services.tax_offset_service import TaxOffsetService


class TaxOffsetServiceTests(unittest.TestCase):
    def test_month_payload_exposes_plan_and_certified_sections(self) -> None:
        service = TaxOffsetService()

        payload = service.get_month_payload("2026-03")

        self.assertIn("input_plan_items", payload)
        self.assertIn("certified_items", payload)
        self.assertIn("certified_matched_rows", payload)
        self.assertIn("certified_outside_plan_rows", payload)
        self.assertIn("locked_certified_input_ids", payload)
        self.assertEqual(payload["locked_certified_input_ids"], ["ti-202603-001"])
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 1)
        self.assertEqual(payload["summary"]["certified_input_tax"], "14,080.00")

    def test_calculate_always_includes_certified_and_only_adds_selected_uncertified(self) -> None:
        service = TaxOffsetService()

        result = service.calculate(
            month="2026-03",
            selected_output_ids=[],
            selected_input_ids=[],
        )

        self.assertEqual(result["summary"]["output_tax"], "41,600.00")
        self.assertEqual(result["summary"]["input_tax"], "14,080.00")
        self.assertEqual(result["summary"]["planned_input_tax"], "0.00")
        self.assertEqual(result["summary"]["certified_input_tax"], "14,080.00")
        self.assertEqual(result["summary"]["deductible_tax"], "14,080.00")
        self.assertEqual(result["summary"]["result_label"], "本月应纳税额")
        self.assertEqual(result["summary"]["result_amount"], "27,520.00")


if __name__ == "__main__":
    unittest.main()
