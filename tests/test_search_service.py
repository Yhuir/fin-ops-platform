import unittest


from fin_ops_platform.services.search_service import SearchService


class SearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.oa_row = {
            "id": "oa-open-001",
            "type": "oa",
            "case_id": "CASE-SEARCH-001",
            "applicant": "陈涛",
            "project_name": "智能工厂项目",
            "expense_type": "设备货款及材料费",
            "expense_content": "PLC 模块采购",
            "apply_type": "支付申请",
            "amount": "58,000.00",
            "counterparty_name": "建设科技有限公司",
            "reason": "PLC 模块采购",
            "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            "summary_fields": {
                "申请人": "陈涛",
                "项目名称": "智能工厂项目",
            },
            "detail_fields": {
                "OA单号": "OA-SEARCH-001",
                "费用类型": "设备货款及材料费",
                "费用内容": "PLC 模块采购",
            },
        }
        self.bank_row = {
            "id": "bk-open-001",
            "type": "bank",
            "case_id": "CASE-SEARCH-001",
            "direction": "支出",
            "trade_time": "2026-03-10 21:27:55",
            "debit_amount": "58,000.00",
            "credit_amount": "",
            "counterparty_name": "建设科技有限公司",
            "payment_account_label": "建设银行 8106",
            "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
            "pay_receive_time": "2026-03-10 21:27:55",
            "remark": "PLC 模块采购",
            "summary_fields": {
                "支付账户": "建设银行 8106",
                "备注": "PLC 模块采购",
            },
            "detail_fields": {
                "企业流水号": "SERIAL-001",
                "账户明细编号-交易流水号": "DETAIL-001",
                "账号": "622200008106",
            },
        }
        self.invoice_row = {
            "id": "iv-open-001",
            "type": "invoice",
            "case_id": "CASE-SEARCH-001",
            "seller_tax_no": "91310000111111111X",
            "seller_name": "建设科技有限公司",
            "buyer_tax_no": "915300007194052520",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-12",
            "amount": "58,000.00",
            "tax_rate": "13%",
            "tax_amount": "7,540.00",
            "total_with_tax": "65,540.00",
            "invoice_type": "进项专票",
            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配付款", "tone": "warn"},
            "detail_fields": {
                "发票号码": "INV-001",
                "数电发票号码": "DIG-001",
                "发票代码": "CODE-001",
            },
        }
        self.ignored_invoice_row = {
            "id": "iv-ignored-001",
            "type": "invoice",
            "case_id": None,
            "seller_tax_no": "91310000999999999X",
            "seller_name": "忽略发票公司",
            "buyer_tax_no": "915300007194052520",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-04-03",
            "amount": "1,250.00",
            "invoice_type": "进项专票",
            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配付款", "tone": "warn"},
            "detail_fields": {
                "发票号码": "INV-IGN-001",
            },
            "ignored": True,
        }
        self.processed_bank_row = {
            "id": "bk-processed-001",
            "type": "bank",
            "case_id": None,
            "direction": "支出",
            "trade_time": "2026-04-05 09:30:00",
            "debit_amount": "1,250.00",
            "credit_amount": "",
            "counterparty_name": "异常供应商",
            "payment_account_label": "建设银行 8826",
            "invoice_relation": {"code": "oa_bank_amount_mismatch", "label": "金额不一致，继续异常", "tone": "danger"},
            "remark": "异常付款",
            "handled_exception": True,
            "detail_fields": {
                "企业流水号": "SERIAL-EX-001",
            },
        }
        self.workbench_rows = {
            "2026-03": [
                {
                    "row": self.oa_row,
                    "zone_hint": "unpaired",
                    "group_id": "case:CASE-SEARCH-001",
                    "project_names": ["智能工厂项目"],
                },
                {
                    "row": self.bank_row,
                    "zone_hint": "unpaired",
                    "group_id": "case:CASE-SEARCH-001",
                    "project_names": ["智能工厂项目"],
                },
                {
                    "row": self.invoice_row,
                    "zone_hint": "unpaired",
                    "group_id": "case:CASE-SEARCH-001",
                    "project_names": ["智能工厂项目"],
                },
            ],
            "2026-04": [
                {
                    "row": self.processed_bank_row,
                    "zone_hint": "processed_exception",
                    "group_id": "group:processed",
                    "project_names": [],
                },
                {
                    "row": self.ignored_invoice_row,
                    "zone_hint": "ignored",
                    "group_id": "",
                    "project_names": [],
                },
            ],
        }
        self.service = SearchService(
            known_months_loader=lambda: ["2026-03", "2026-04"],
            canonical_rows_loader=lambda month: self.workbench_rows[month],
        )

    def test_search_finds_oa_rows_by_keyword_and_builds_jump_target(self) -> None:
        payload = self.service.search(q="陈涛", month="all")

        self.assertEqual(payload["summary"]["oa"], 1)
        self.assertEqual(payload["summary"]["bank"], 0)
        self.assertEqual(payload["summary"]["invoice"], 0)
        result = payload["oa_results"][0]
        self.assertEqual(result["row_id"], "oa-open-001")
        self.assertEqual(result["zone_hint"], "unpaired")
        self.assertEqual(result["matched_field"], "申请人")
        self.assertEqual(result["jump_target"]["month"], "2026-03")
        self.assertEqual(result["jump_target"]["row_id"], "oa-open-001")

    def test_search_matches_bank_rows_across_company_amount_serial_and_account_last4(self) -> None:
        company_payload = self.service.search(q="建设科技", month="2026-03", scope="bank")
        amount_payload = self.service.search(q="58000", month="2026-03", scope="bank")
        serial_payload = self.service.search(q="SERIAL-001", month="2026-03", scope="bank")
        last4_payload = self.service.search(q="8106", month="2026-03", scope="bank")

        self.assertEqual(company_payload["bank_results"][0]["matched_field"], "对方户名")
        self.assertEqual(amount_payload["bank_results"][0]["matched_field"], "金额")
        self.assertEqual(serial_payload["bank_results"][0]["matched_field"], "企业流水号")
        self.assertEqual(last4_payload["bank_results"][0]["matched_field"], "支付账户")

    def test_grouped_search_indexes_bank_flow_collapsed_rows_and_returns_group_context(self) -> None:
        original_bank_row = {
            **self.bank_row,
            "id": "bk-collapsed-001",
            "case_id": "bank_flow_batch_fee_search",
            "remark": "折叠明细唯一备注",
            "detail_fields": {"企业流水号": "NO-OA-COLLAPSED-SERIAL"},
            "invoice_relation": {"code": "bank_flow_rule_batch", "label": "流水规则批次", "tone": "success"},
        }
        summary_row = {
            "id": "bank_flow_rule_summary:bank_flow_batch_fee_search",
            "type": "bank",
            "source_kind": "bank_flow_rule_batch_summary",
            "label": "流水规则 · 手续费",
            "amount": "58,000.00",
            "counterparty_name": "建设银行 8106",
            "trade_time": "2026-03",
            "invoice_relation": {"code": "bank_flow_rule_batch", "label": "流水规则批次", "tone": "success"},
            "special_metadata": {
                "source_batch_id": "bank_flow_batch_fee_search",
                "relation_mode": "bank_flow_rule_batch",
                "batch_type": "fee",
                "batch_label": "手续费",
                "row_count": 1,
                "total_amount": "58,000.00",
                "withdrawable": True,
            },
        }
        service = SearchService(
            known_months_loader=lambda: ["2026-03"],
            canonical_rows_loader=lambda _month: [
                {
                    "row": original_bank_row,
                    "zone_hint": "paired",
                    "group_id": "case:bank_flow_batch_fee_search",
                    "project_names": [],
                }
            ],
        )

        payload = service.search(q="NO-OA-COLLAPSED-SERIAL", month="2026-03", scope="bank")

        self.assertEqual(payload["summary"]["bank"], 1)
        self.assertEqual([result["row_id"] for result in payload["bank_results"]], ["bk-collapsed-001"])
        result = payload["bank_results"][0]
        self.assertNotEqual(result["row_id"], summary_row["id"])
        self.assertEqual(result["zone_hint"], "paired")
        self.assertEqual(result["group_id"], "case:bank_flow_batch_fee_search")
        self.assertEqual(result["jump_target"]["group_id"], "case:bank_flow_batch_fee_search")

    def test_narrow_workbench_rows_preserve_project_status_group_and_cache_semantics(self) -> None:
        load_calls: list[str] = []
        service = SearchService(
            known_months_loader=lambda: ["2026-03"],
            canonical_rows_loader=lambda month: load_calls.append(month)
            or [
                {
                    "row": self.bank_row,
                    "zone_hint": "paired",
                    "group_id": "case:CASE-SEARCH-001",
                    "project_names": ["智能工厂项目"],
                },
                {
                    "row": self.ignored_invoice_row,
                    "zone_hint": "ignored",
                    "group_id": "",
                    "project_names": [],
                },
            ],
        )

        first = service.search(
            q="SERIAL-001",
            month="2026-03",
            scope="bank",
            project_name="智能工厂项目",
            status="paired",
        )
        second = service.search(
            q="SERIAL-001",
            month="2026-03",
            scope="bank",
            project_name="智能工厂项目",
            status="paired",
        )
        ignored = service.search(q="INV-IGN-001", month="2026-03", status="ignored")

        self.assertEqual(load_calls, ["2026-03"])
        self.assertEqual(first, second)
        self.assertEqual(first["bank_results"][0]["group_id"], "case:CASE-SEARCH-001")
        self.assertEqual(first["bank_results"][0]["zone_hint"], "paired")
        self.assertEqual(ignored["invoice_results"][0]["zone_hint"], "ignored")

        service.clear_cache()
        service.search(q="SERIAL-001", month="2026-03", scope="bank")

        self.assertEqual(load_calls, ["2026-03", "2026-03"])

    def test_search_matches_invoice_rows_by_invoice_number_company_and_tax_no(self) -> None:
        invoice_no_payload = self.service.search(q="INV-001", month="2026-03", scope="invoice")
        company_payload = self.service.search(q="建设科技有限公司", month="2026-03", scope="invoice")
        tax_no_payload = self.service.search(q="91310000111111111X", month="2026-03", scope="invoice")

        self.assertEqual(invoice_no_payload["invoice_results"][0]["matched_field"], "发票号码")
        self.assertEqual(company_payload["invoice_results"][0]["matched_field"], "销方名称")
        self.assertEqual(tax_no_payload["invoice_results"][0]["matched_field"], "销方识别号")

    def test_search_supports_status_filter_for_ignored_and_processed_exception_rows(self) -> None:
        ignored_payload = self.service.search(q="INV-IGN-001", month="all", status="ignored")
        processed_payload = self.service.search(q="SERIAL-EX-001", month="all", status="processed_exception")

        self.assertEqual(ignored_payload["summary"]["invoice"], 1)
        self.assertEqual(ignored_payload["invoice_results"][0]["zone_hint"], "ignored")
        self.assertEqual(processed_payload["summary"]["bank"], 1)
        self.assertEqual(processed_payload["bank_results"][0]["zone_hint"], "processed_exception")

    def test_search_stops_scanning_extra_months_after_scope_limit_is_reached(self) -> None:
        load_calls: list[str] = []
        matching_bank_row = {
            "id": "bk-any",
            "type": "bank",
            "case_id": None,
            "direction": "支出",
            "trade_time": "2026-03-10 21:27:55",
            "debit_amount": "58,000.00",
            "credit_amount": "",
            "counterparty_name": "建设科技有限公司",
            "payment_account_label": "建设银行 8106",
            "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
            "remark": "PLC 模块采购",
            "detail_fields": {
                "企业流水号": "SERIAL-001",
            },
        }
        rows_by_month = {
            month: [{"row": matching_bank_row, "zone_hint": "unpaired", "group_id": "", "project_names": []}]
            for month in ("2026-05", "2026-04", "2026-03")
        }
        service = SearchService(
            known_months_loader=lambda: ["2026-05", "2026-04", "2026-03"],
            canonical_rows_loader=lambda month: load_calls.append(month) or rows_by_month[month],
        )

        payload = service.search(q="建设科技", month="all", scope="bank", limit=1)

        self.assertEqual(payload["summary"]["bank"], 1)
        self.assertEqual(load_calls, ["2026-05"])

    def test_search_reuses_cached_month_indexes_and_queries(self) -> None:
        month_calls: list[str] = []
        months_calls = 0

        def load_months() -> list[str]:
            nonlocal months_calls
            months_calls += 1
            return ["2026-03", "2026-04"]

        service = SearchService(
            known_months_loader=load_months,
            canonical_rows_loader=lambda month: month_calls.append(month) or self.workbench_rows[month],
        )

        first_payload = service.search(q="建设科技", month="all", scope="bank")
        second_payload = service.search(q="建设科技", month="all", scope="bank")

        self.assertEqual(first_payload["summary"]["bank"], 1)
        self.assertEqual(second_payload["summary"]["bank"], 1)
        self.assertEqual(months_calls, 1)
        self.assertEqual(month_calls, ["2026-04", "2026-03"])

    def test_clear_cache_forces_search_to_reload_months(self) -> None:
        month_calls: list[str] = []

        service = SearchService(
            known_months_loader=lambda: ["2026-03"],
            canonical_rows_loader=lambda month: month_calls.append(month) or self.workbench_rows[month],
        )

        service.search(q="建设科技", month="all", scope="bank")
        service.clear_cache()
        service.search(q="建设科技", month="all", scope="bank")

        self.assertEqual(month_calls, ["2026-03", "2026-03"])


if __name__ == "__main__":
    unittest.main()
