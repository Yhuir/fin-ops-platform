import json
import unittest

from fin_ops_platform.app.server import build_application


class SearchApiTests(unittest.TestCase):
    def test_search_api_returns_grouped_entity_results(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/search?q=%E5%8D%8E%E4%B8%9C%E8%AE%BE%E5%A4%87%E4%BE%9B%E5%BA%94%E5%95%86&month=2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "华东设备供应商")
        self.assertGreaterEqual(payload["summary"]["oa"], 1)
        self.assertGreaterEqual(payload["summary"]["bank"], 1)
        self.assertGreaterEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["oa_results"][0]["jump_target"]["month"], "2026-03")
        self.assertIn(payload["oa_results"][0]["zone_hint"], {"paired", "open"})
        self.assertIsInstance(payload["oa_results"][0]["primary_meta"], str)
        self.assertIsInstance(payload["oa_results"][0]["secondary_meta"], str)
        self.assertIsInstance(payload["bank_results"][0]["primary_meta"], str)
        self.assertIsInstance(payload["bank_results"][0]["secondary_meta"], str)

    def test_search_api_supports_status_filter_for_ignored_rows(self) -> None:
        app = build_application()
        raw_payload = app._build_raw_workbench_payload("2026-03")
        target_row = raw_payload["open"]["invoice"][0]
        app._workbench_override_service.ignore_row(row=target_row, comment="测试忽略")

        response = app.handle_request("GET", "/api/search?q=12561048&month=2026-03&status=ignored")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["invoice_results"][0]["zone_hint"], "ignored")
        self.assertEqual(payload["invoice_results"][0]["status_label"], "已忽略")


if __name__ == "__main__":
    unittest.main()
