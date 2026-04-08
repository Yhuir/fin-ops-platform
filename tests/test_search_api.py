import json
import unittest
from unittest.mock import patch

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

    def test_search_api_uses_cached_read_model_and_ignored_rows_without_raw_rebuild(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[
                {
                    "id": "iv-ignored-001",
                    "type": "invoice",
                    "seller_name": "云南服务商有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "amount": "600.00",
                    "issue_date": "2026-03-20",
                    "invoice_type": "进项发票",
                    "ignored": True,
                    "detail_fields": {
                        "发票号码": "12561048",
                        "发票代码": "5300261130",
                    },
                }
            ],
            generated_at="2026-04-08T12:00:00+00:00",
        )

        with patch.object(app, "_build_raw_workbench_payload", side_effect=AssertionError("should not rebuild raw payload")):
            response = app.handle_request("GET", "/api/search?q=12561048&month=2026-03&status=ignored")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["invoice_results"][0]["row_id"], "iv-ignored-001")
        self.assertEqual(payload["invoice_results"][0]["zone_hint"], "ignored")


if __name__ == "__main__":
    unittest.main()
