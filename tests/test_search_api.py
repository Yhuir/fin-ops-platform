import json
import unittest
from unittest.mock import patch

from tests.app_test_support import build_local_state_application as build_application


class SearchWorkbenchRowsRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.scope_keys: list[str] = []

    def list_workbench_search_rows(self, *, scope_key: str) -> list[dict[str, object]]:
        self.scope_keys.append(scope_key)
        return list(self.rows)


class SearchApiTests(unittest.TestCase):
    def test_search_api_returns_grouped_entity_results(self) -> None:
        app = build_application()
        repository = SearchWorkbenchRowsRepository(
            [
                {
                    "row": {
                        "id": "oa-search-1",
                        "type": "oa",
                        "project_name": "华东升级项目",
                        "applicant": "张三",
                        "counterparty_name": "华东设备供应商",
                        "amount": "100.00",
                    },
                    "zone_hint": "paired",
                    "group_id": "case:SEARCH-1",
                    "project_names": ["华东升级项目"],
                },
                {
                    "row": {
                        "id": "bank-search-1",
                        "type": "bank",
                        "counterparty_name": "华东设备供应商",
                        "trade_time": "2026-03-10 10:00:00",
                        "debit_amount": "100.00",
                        "direction": "支出",
                    },
                    "zone_hint": "paired",
                    "group_id": "case:SEARCH-1",
                    "project_names": ["华东升级项目"],
                },
                {
                    "row": {
                        "id": "invoice-search-1",
                        "type": "invoice",
                        "seller_name": "华东设备供应商",
                        "buyer_name": "云南溯源科技有限公司",
                        "amount": "100.00",
                    },
                    "zone_hint": "paired",
                    "group_id": "case:SEARCH-1",
                    "project_names": ["华东升级项目"],
                },
            ]
        )
        app._workbench_sql_read_repository = repository

        response = app.handle_request("GET", "/api/search?q=%E5%8D%8E%E4%B8%9C%E8%AE%BE%E5%A4%87%E4%BE%9B%E5%BA%94%E5%95%86&month=2026-03")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["query"], "华东设备供应商")
        self.assertGreaterEqual(payload["summary"]["oa"], 1)
        self.assertGreaterEqual(payload["summary"]["bank"], 1)
        self.assertGreaterEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["oa_results"][0]["jump_target"]["month"], "2026-03")
        self.assertIn(payload["oa_results"][0]["zone_hint"], {"paired", "unpaired"})
        self.assertIsInstance(payload["oa_results"][0]["primary_meta"], str)
        self.assertIsInstance(payload["oa_results"][0]["secondary_meta"], str)
        self.assertIsInstance(payload["bank_results"][0]["primary_meta"], str)
        self.assertIsInstance(payload["bank_results"][0]["secondary_meta"], str)
        self.assertEqual(repository.scope_keys, ["2026-03"])

    def test_search_api_supports_status_filter_for_ignored_rows(self) -> None:
        app = build_application()
        app._workbench_sql_read_repository = SearchWorkbenchRowsRepository(
            [
                {
                    "row": {
                        "id": "iv-ignored-001",
                        "type": "invoice",
                        "seller_name": "云南服务商有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "amount": "600.00",
                        "issue_date": "2026-03-20",
                        "invoice_type": "进项发票",
                        "ignored": True,
                        "detail_fields": {"发票号码": "12561048", "发票代码": "5300261130"},
                    },
                    "zone_hint": "ignored",
                    "group_id": "",
                    "project_names": [],
                }
            ]
        )

        response = app.handle_request("GET", "/api/search?q=12561048&month=2026-03&status=ignored")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["invoice_results"][0]["zone_hint"], "ignored")
        self.assertEqual(payload["invoice_results"][0]["status_label"], "已忽略")

    def test_search_api_uses_narrow_workbench_rows_without_raw_rebuild(self) -> None:
        app = build_application()
        repository = SearchWorkbenchRowsRepository(
            [
                {
                    "row": {
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
                    },
                    "zone_hint": "ignored",
                    "group_id": "",
                    "project_names": [],
                },
            ]
        )
        app._workbench_sql_read_repository = repository

        response = app.handle_request("GET", "/api/search?q=12561048&month=2026-03&status=ignored")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["invoice"], 1)
        self.assertEqual(payload["invoice_results"][0]["row_id"], "iv-ignored-001")
        self.assertEqual(payload["invoice_results"][0]["zone_hint"], "ignored")
        self.assertEqual(repository.scope_keys, ["2026-03"])


if __name__ == "__main__":
    unittest.main()
