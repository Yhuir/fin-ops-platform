import json
import unittest

from fin_ops_platform.app.server import build_application


class TaxOffsetApiTests(unittest.TestCase):
    def test_get_tax_offset_returns_month_rows_and_certified_plan_sections(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/tax-offset?month=2026-03")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["month"], "2026-03")
        self.assertGreater(len(payload["output_items"]), 0)
        self.assertGreater(len(payload["input_plan_items"]), 0)
        self.assertGreater(len(payload["certified_items"]), 0)
        self.assertIn("certified_matched_rows", payload)
        self.assertIn("certified_outside_plan_rows", payload)
        self.assertEqual(len(payload["certified_outside_plan_rows"]), 1)
        self.assertEqual(payload["locked_certified_input_ids"], ["ti-202603-001"])
        self.assertEqual(payload["default_selected_output_ids"], [item["id"] for item in payload["output_items"]])
        self.assertEqual(payload["default_selected_input_ids"], ["ti-202603-002"])
        self.assertEqual(payload["summary"]["certified_input_tax"], "14,080.00")

    def test_calculate_tax_offset_includes_certified_items_even_when_not_selected(self) -> None:
        app = build_application()

        response = app.handle_request(
            "POST",
            "/api/tax-offset/calculate",
            json.dumps(
                {
                    "month": "2026-03",
                    "selected_output_ids": [],
                    "selected_input_ids": [],
                }
            ),
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["summary"]["output_tax"], "41,600.00")
        self.assertEqual(payload["summary"]["input_tax"], "14,080.00")
        self.assertEqual(payload["summary"]["planned_input_tax"], "0.00")
        self.assertEqual(payload["summary"]["certified_input_tax"], "14,080.00")
        self.assertEqual(payload["summary"]["deductible_tax"], "14,080.00")
        self.assertEqual(payload["summary"]["result_label"], "本月应纳税额")
        self.assertEqual(payload["summary"]["result_amount"], "27,520.00")


if __name__ == "__main__":
    unittest.main()
