from io import BytesIO
import json
from urllib.parse import quote
import unittest

from openpyxl import load_workbook

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes


class _CostStatsOAAdapter:
    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if month != "2026-03":
            return []
        return [
            OAApplicationRecord(
                id="oa-cost-api-001",
                month="2026-03",
                section="paired",
                case_id="CASE-COST-001",
                applicant="刘际涛",
                project_name="云南溯源科技",
                apply_type="日常报销",
                amount="1250",
                counterparty_name="昆明设备供应商",
                reason="PLC 模块采购",
                relation_code="fully_linked",
                relation_label="完全关联",
                relation_tone="success",
                expense_type="设备货款及材料费",
                expense_content="PLC 模块采购",
                detail_fields={
                    "费用类型": "设备货款及材料费",
                    "费用内容": "PLC 模块采购",
                },
            )
        ]


class _FallbackCostStatsOAAdapter:
    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        if month != "2026-03":
            return []
        return [
            OAApplicationRecord(
                id="oa-cost-fallback-001",
                month="2026-03",
                section="open",
                case_id=None,
                applicant="刘际涛",
                project_name="云南溯源科技",
                apply_type="支付申请",
                amount="1250",
                counterparty_name="昆明设备供应商",
                reason="PLC 模块采购",
                relation_code="pending_match",
                relation_label="待找流水与发票",
                relation_tone="warn",
                expense_type="",
                expense_content="",
                detail_fields={
                    "费用类型": "设备货款及材料费",
                    "费用内容": "PLC 模块采购",
                },
            )
        ]


class CostStatisticsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_application()
        self.app._workbench_query_service = self.app._workbench_query_service.__class__(oa_adapter=_CostStatsOAAdapter())
        self.app._workbench_api_routes = WorkbenchApiRoutes(
            self.app._workbench_query_service,
            self.app._workbench_action_service,
        )
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        self.app._cost_statistics_service = CostStatisticsService(
            self.app._import_service,
            grouped_workbench_loader=self.app._build_api_workbench_payload,
            row_detail_loader=self.app._get_api_workbench_row_detail_payload,
        )

    def test_get_cost_statistics_routes_return_expected_shapes(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-statistics.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        payload = json.loads(self.app.handle_request("GET", "/api/cost-statistics?month=2026-03").body)
        self.assertEqual(payload["month"], "2026-03")
        self.assertEqual(payload["summary"]["row_count"], 1)
        self.assertEqual(payload["rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(payload["rows"][0]["expense_type"], "设备货款及材料费")

        project_name = quote("云南溯源科技", safe="")
        project_payload = json.loads(
            self.app.handle_request("GET", f"/api/cost-statistics/projects/{project_name}?month=2026-03").body
        )
        self.assertEqual(project_payload["project_name"], "云南溯源科技")
        self.assertEqual(project_payload["rows"][0]["expense_content"], "PLC 模块采购")
        transaction_id = project_payload["rows"][0]["transaction_id"]

        detail_payload = json.loads(
            self.app.handle_request("GET", f"/api/cost-statistics/transactions/{transaction_id}").body
        )
        self.assertEqual(detail_payload["transaction"]["id"], transaction_id)
        self.assertEqual(detail_payload["transaction"]["project_name"], "云南溯源科技")
        self.assertEqual(detail_payload["transaction"]["expense_type"], "设备货款及材料费")

        explorer_payload = json.loads(self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03").body)
        self.assertEqual(explorer_payload["month"], "2026-03")
        self.assertEqual(explorer_payload["summary"]["transaction_count"], 1)
        self.assertEqual(explorer_payload["time_rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(explorer_payload["project_rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(explorer_payload["expense_type_rows"][0]["expense_type"], "设备货款及材料费")

    def test_cost_statistics_export_returns_xlsx_for_each_view(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        month_response = self.app.handle_request("GET", "/api/cost-statistics/export?month=2026-03&view=month")
        self.assertEqual(month_response.status_code, 200)
        self.assertEqual(
            month_response.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("filename*=", month_response.headers["Content-Disposition"])
        self.assertIn("%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%9C%88%E4%BB%BD%E6%B1%87%E6%80%BB.xlsx", month_response.headers["Content-Disposition"])
        self.assertIsInstance(month_response.headers["Content-Disposition"].encode("latin-1"), bytes)
        month_workbook = load_workbook(BytesIO(month_response.body))
        month_sheet = month_workbook.active
        self.assertEqual(month_sheet.title, "月份汇总")
        self.assertEqual(month_sheet["A2"].value, "云南溯源科技")
        self.assertEqual(month_sheet["B2"].value, "设备货款及材料费")

        project_name = quote("云南溯源科技", safe="")
        project_response = self.app.handle_request(
            "GET",
            f"/api/cost-statistics/export?month=2026-03&view=project&project_name={project_name}",
        )
        self.assertEqual(project_response.status_code, 200)
        self.assertIn("filename*=", project_response.headers["Content-Disposition"])
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E9%A1%B9%E7%9B%AE%E6%98%8E%E7%BB%86_%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80.xlsx",
            project_response.headers["Content-Disposition"],
        )
        project_workbook = load_workbook(BytesIO(project_response.body))
        self.assertEqual(
            project_workbook.sheetnames,
            [
                "导出说明",
                "项目汇总",
                "按费用类型汇总",
                "按费用内容汇总",
                "流水明细",
                "OA关联明细",
                "发票关联明细",
                "异常与未闭环",
            ],
        )
        summary_sheet = project_workbook["项目汇总"]
        self.assertEqual(summary_sheet["A2"].value, "项目名称")
        self.assertEqual(summary_sheet["B2"].value, "云南溯源科技")
        transaction_sheet = project_workbook["流水明细"]
        self.assertEqual(transaction_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(transaction_sheet["B2"].value, "txn_imported_0001")
        self.assertEqual(transaction_sheet["H2"].value, "云南溯源科技")
        self.assertEqual(transaction_sheet["I2"].value, "设备货款及材料费")

        transaction_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export?month=2026-03&view=transaction&transaction_id=txn_imported_0001",
        )
        self.assertEqual(transaction_response.status_code, 200)
        self.assertIn("filename*=", transaction_response.headers["Content-Disposition"])
        transaction_workbook = load_workbook(BytesIO(transaction_response.body))
        detail_sheet = transaction_workbook.active
        self.assertEqual(detail_sheet.title, "流水详情")
        self.assertEqual(detail_sheet["A2"].value, "交易ID")
        self.assertEqual(detail_sheet["B2"].value, "txn_imported_0001")

        time_response = self.app.handle_request("GET", "/api/cost-statistics/export?month=2026-03&view=time")
        self.assertEqual(time_response.status_code, 200)
        self.assertIn("filename*=", time_response.headers["Content-Disposition"])
        self.assertIn("%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx", time_response.headers["Content-Disposition"])
        time_workbook = load_workbook(BytesIO(time_response.body))
        time_sheet = time_workbook.active
        self.assertEqual(time_sheet.title, "按时间统计")
        self.assertEqual(time_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(time_sheet["B2"].value, "云南溯源科技")

        expense_type = quote("设备货款及材料费", safe="")
        expense_response = self.app.handle_request(
            "GET",
            f"/api/cost-statistics/export?month=2026-03&view=expense_type&expense_type={expense_type}",
        )
        self.assertEqual(expense_response.status_code, 200)
        self.assertIn("filename*=", expense_response.headers["Content-Disposition"])
        expense_workbook = load_workbook(BytesIO(expense_response.body))
        expense_sheet = expense_workbook.active
        self.assertEqual(expense_sheet.title, "按费用类型统计")
        self.assertEqual(expense_sheet["A2"].value, "2026-03-10 21:27:55")
        self.assertEqual(expense_sheet["B2"].value, "云南溯源科技")

    def test_project_export_honors_advanced_export_options(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-advanced.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-ADV-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        project_name = quote("云南溯源科技", safe="")
        response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                "&start_month=2026-03"
                "&end_month=2026-04"
                "&include_oa_details=false"
                "&include_invoice_details=false"
                "&include_exception_rows=false"
                "&include_ignored_rows=false"
                "&include_expense_content_summary=false"
                "&sort_by=amount_desc"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("filename*=", response.headers["Content-Disposition"])
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03%E8%87%B32026-04_%E9%A1%B9%E7%9B%AE%E6%98%8E%E7%BB%86_%E4%BA%91%E5%8D%97%E6%BA%AF%E6%BA%90%E7%A7%91%E6%8A%80.xlsx",
            response.headers["Content-Disposition"],
        )
        workbook = load_workbook(BytesIO(response.body))
        self.assertEqual(
            workbook.sheetnames,
            [
                "导出说明",
                "项目汇总",
                "按费用类型汇总",
                "流水明细",
            ],
        )

    def test_cost_statistics_export_preview_supports_filtered_views(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-preview.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-PREVIEW-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        project_name = quote("云南溯源科技", safe="")
        preview_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export-preview"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                f"&expense_type={quote('设备货款及材料费', safe='')}"
            ),
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["view"], "project")
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertIn("项目汇总", preview_payload["sheet_names"])
        self.assertEqual(preview_payload["columns"][0], "时间")
        self.assertEqual(preview_payload["rows"][0][0], "2026-03-10 21:27:55")

        expense_preview_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export-preview"
                "?month=all"
                "&view=expense_type"
                "&start_month=2026-03"
                "&end_month=2026-04"
                f"&expense_type={quote('设备货款及材料费', safe='')}"
            ),
        )
        self.assertEqual(expense_preview_response.status_code, 200)
        expense_preview_payload = json.loads(expense_preview_response.body)
        self.assertEqual(expense_preview_payload["view"], "expense_type")
        self.assertEqual(expense_preview_payload["sheet_names"], ["按费用类型统计"])

    def test_cost_statistics_export_preview_and_export_support_exact_date_range(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-date-range.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-DATE-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        preview_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export-preview?month=all&view=time&start_date=2026-03-10&end_date=2026-03-10",
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["scope_label"], "2026-03-10至2026-03-10")
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertEqual(preview_payload["rows"][0][0], "2026-03-10 21:27:55")

        export_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/export?month=all&view=time&start_date=2026-03-10&end_date=2026-03-10",
        )
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(
            "%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_2026-03-10%E8%87%B32026-03-10_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx",
            export_response.headers["Content-Disposition"],
        )

    def test_export_filters_project_and_expense_type_views_by_expense_types(self) -> None:
        from fin_ops_platform.domain.enums import BatchType

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-export-filtered.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-EXPORT-FILTER-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)

        project_name = quote("云南溯源科技", safe="")
        expense_type = quote("设备货款及材料费", safe="")
        project_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=project"
                f"&project_name={project_name}"
                f"&expense_type={expense_type}"
            ),
        )
        self.assertEqual(project_response.status_code, 200)
        project_workbook = load_workbook(BytesIO(project_response.body))
        project_transaction_sheet = project_workbook["流水明细"]
        self.assertEqual(project_transaction_sheet.max_row, 2)
        self.assertEqual(project_transaction_sheet["I2"].value, "设备货款及材料费")

        expense_response = self.app.handle_request(
            "GET",
            (
                "/api/cost-statistics/export"
                "?month=all"
                "&view=expense_type"
                "&start_month=2026-03"
                "&end_month=2026-04"
                f"&expense_type={expense_type}"
            ),
        )
        self.assertEqual(expense_response.status_code, 200)
        expense_workbook = load_workbook(BytesIO(expense_response.body))
        expense_sheet = expense_workbook.active
        self.assertEqual(expense_sheet.title, "按费用类型统计")
        self.assertEqual(expense_sheet.max_row, 2)
        self.assertEqual(expense_sheet["D2"].value, "PLC 模块采购")

    def test_cost_statistics_uses_oa_detail_fields_after_manual_confirm_link(self) -> None:
        from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes
        from fin_ops_platform.domain.enums import BatchType

        app = build_application()
        app._workbench_query_service = app._workbench_query_service.__class__(oa_adapter=_FallbackCostStatsOAAdapter())
        app._workbench_api_routes = WorkbenchApiRoutes(
            app._workbench_query_service,
            app._workbench_action_service,
        )
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        app._cost_statistics_service = CostStatisticsService(
            app._import_service,
            grouped_workbench_loader=app._build_api_workbench_payload,
            row_detail_loader=app._get_api_workbench_row_detail_payload,
        )

        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-fallback.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62229999",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-FALLBACK-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": ["oa-cost-fallback-001", "txn_imported_0001"],
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)

        payload = json.loads(app.handle_request("GET", "/api/cost-statistics?month=2026-03").body)
        self.assertEqual(payload["summary"]["row_count"], 1)
        self.assertEqual(payload["rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(payload["rows"][0]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["rows"][0]["expense_content"], "PLC 模块采购")


if __name__ == "__main__":
    unittest.main()
