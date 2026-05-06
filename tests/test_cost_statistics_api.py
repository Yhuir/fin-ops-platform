from io import BytesIO
import json
from types import SimpleNamespace
from unittest.mock import patch
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


class _MemoryCostStatisticsReadModelService:
    def __init__(self) -> None:
        self.read_models: dict[str, dict[str, object]] = {}

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object] | None):
        service = cls()
        if isinstance(snapshot, dict):
            read_models = snapshot.get("read_models")
            if isinstance(read_models, dict):
                service.read_models = {str(key): dict(value) for key, value in read_models.items()}
        return service

    def snapshot(self) -> dict[str, object]:
        return {"read_models": {key: dict(value) for key, value in self.read_models.items()}}

    def snapshot_scope_keys(self, scope_keys: list[str]) -> dict[str, object]:
        return {"read_models": {key: dict(self.read_models[key]) for key in scope_keys if key in self.read_models}}

    def scope_key(self, month: str, project_scope: str) -> str:
        return f"{project_scope}:{month}"

    def get_read_model(self, month: str, project_scope: str) -> dict[str, object] | None:
        return self.read_models.get(self.scope_key(month, project_scope))

    def upsert_read_model(
        self,
        month: str,
        project_scope: str,
        payload: dict[str, object],
        generated_at: str | None = None,
        source_scope_keys: list[str] | None = None,
        cache_status: str = "ready",
    ) -> dict[str, object]:
        scope_key = self.scope_key(month, project_scope)
        read_model = {
            "scope_key": scope_key,
            "month": month,
            "project_scope": project_scope,
            "payload": payload,
            "generated_at": generated_at,
            "source_scope_keys": list(source_scope_keys or []),
            "cache_status": cache_status,
        }
        self.read_models[scope_key] = read_model
        return read_model

    def invalidate_months(
        self,
        months: list[str],
        project_scopes: list[str] | None = None,
        include_all: bool = True,
    ) -> list[str]:
        scopes = list(project_scopes or ["active", "all"])
        targets = set()
        for month in months:
            for scope in scopes:
                targets.add(self.scope_key(str(month), str(scope)))
        if include_all:
            for scope in scopes:
                targets.add(self.scope_key("all", str(scope)))
        deleted = []
        for scope_key in sorted(targets):
            if scope_key in self.read_models:
                deleted.append(scope_key)
                del self.read_models[scope_key]
        return deleted

    def clear(self) -> list[str]:
        deleted = sorted(self.read_models)
        self.read_models.clear()
        return deleted

    def list_scope_keys(self) -> list[str]:
        return sorted(self.read_models)

    def list_read_model_metadata(self) -> list[dict[str, object]]:
        return [
            {key: value for key, value in read_model.items() if key != "payload"}
            for read_model in self.read_models.values()
        ]


class CostStatisticsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = build_application()
        self.app._cost_statistics_read_model_service = _MemoryCostStatisticsReadModelService()
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
            project_active_checker=self.app._app_settings_service.is_project_active,
        )

    def test_cost_statistics_explorer_cache_hit_does_not_rebuild(self) -> None:
        cached_payload = {
            "month": "2026-03",
            "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "88.00"},
            "time_rows": [{"transaction_id": "cached-sentinel"}],
            "project_rows": [],
            "expense_type_rows": [],
        }
        self.app._cost_statistics_read_model_service.upsert_read_model("2026-03", "active", cached_payload)

        with patch.object(
            self.app._cost_statistics_service,
            "get_explorer",
            side_effect=AssertionError("should not rebuild cached explorer"),
        ):
            response = self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["time_rows"][0]["transaction_id"], "cached-sentinel")

    def test_cost_statistics_explorer_miss_writes_cache_and_logs_hit_metrics(self) -> None:
        calls: list[tuple[str, str]] = []

        def build_explorer(month: str, *, project_scope: str) -> dict[str, object]:
            calls.append((month, project_scope))
            return {
                "month": month,
                "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "120.00"},
                "time_rows": [{"transaction_id": "txn-1"}, {"transaction_id": "txn-2"}],
                "project_rows": [],
                "expense_type_rows": [],
            }

        self.app._cost_statistics_service = SimpleNamespace(get_explorer=build_explorer)

        with patch("builtins.print") as print_mock:
            first_response = self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03")
            second_response = self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03")

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(calls, [("2026-03", "active")])
        self.assertEqual(
            json.loads(second_response.body)["time_rows"],
            [{"transaction_id": "txn-1"}, {"transaction_id": "txn-2"}],
        )
        metric_payloads = [
            json.loads(call.args[0])
            for call in print_mock.call_args_list
            if call.args and json.loads(call.args[0]).get("kind") == "cost_statistics_explorer_metric"
        ]
        self.assertEqual([payload["cache_hit"] for payload in metric_payloads], [False, True])
        self.assertEqual([payload["entry_count"] for payload in metric_payloads], [2, 2])

    def test_cost_statistics_all_month_cache_miss_returns_empty_payload_and_schedules_warmup(self) -> None:
        self.app._cost_statistics_service = SimpleNamespace(
            get_explorer=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("all should warm asynchronously")),
        )
        job = SimpleNamespace(job_id="warmup-job-1", owner_user_id="system")

        with (
            patch.object(
                self.app._background_job_service,
                "create_or_get_idempotent_job_with_created",
                return_value=(job, True),
            ) as create_job,
            patch.object(self.app._background_job_service, "run_job") as run_job,
        ):
            response = self.app.handle_request("GET", "/api/cost-statistics/explorer?month=all&project_scope=active")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["summary"], {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"})
        self.assertEqual(payload["time_rows"], [])
        self.assertEqual(payload["project_rows"], [])
        self.assertEqual(payload["expense_type_rows"], [])
        create_job.assert_called_once()
        self.assertEqual(create_job.call_args.kwargs["job_type"], "cost_statistics_cache_warmup")
        self.assertIn("all", create_job.call_args.kwargs["idempotency_key"])
        run_job.assert_called_once()

    def test_workbench_scope_invalidation_deletes_cost_statistics_month_and_all_models_and_schedules_warmup(self) -> None:
        service = self.app._cost_statistics_read_model_service
        for month in ("2026-03", "all"):
            for project_scope in ("active", "all"):
                service.upsert_read_model(
                    month,
                    project_scope,
                    {
                        "month": month,
                        "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "1.00"},
                        "time_rows": [{"transaction_id": f"{project_scope}-{month}"}],
                        "project_rows": [],
                        "expense_type_rows": [],
                    },
                )

        with patch.object(self.app, "_schedule_cost_statistics_cache_warmup") as schedule_warmup:
            deleted_workbench_scopes = self.app._invalidate_workbench_read_model_scopes(["2026-03"])

        self.assertEqual(deleted_workbench_scopes, ["2026-03"])
        self.assertIsNone(service.get_read_model("2026-03", "active"))
        self.assertIsNone(service.get_read_model("2026-03", "all"))
        self.assertIsNone(service.get_read_model("all", "active"))
        self.assertIsNone(service.get_read_model("all", "all"))
        schedule_warmup.assert_called_once()
        self.assertCountEqual(schedule_warmup.call_args.args[0], ["2026-03", "all"])

        for project_scope in ("active", "all"):
            service.upsert_read_model(
                "all",
                project_scope,
                {
                    "month": "all",
                    "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "1.00"},
                    "time_rows": [{"transaction_id": f"{project_scope}-all-rebuilt"}],
                    "project_rows": [],
                    "expense_type_rows": [],
                },
            )

        with patch.object(self.app, "_schedule_cost_statistics_cache_warmup") as schedule_warmup:
            self.app._invalidate_workbench_read_model_scopes(["all"])

        self.assertIsNone(service.get_read_model("all", "active"))
        self.assertIsNone(service.get_read_model("all", "all"))
        schedule_warmup.assert_called_once()
        self.assertEqual(schedule_warmup.call_args.args[0], ["all"])

    def test_import_preview_does_not_invalidate_cost_statistics_cache(self) -> None:
        with (
            patch.object(self.app, "_invalidate_cost_statistics_read_models") as invalidate_all,
            patch.object(self.app, "_invalidate_cost_statistics_read_model_scopes") as invalidate_scopes,
        ):
            response = self.app.handle_request(
                "POST",
                "/imports/preview",
                json.dumps(
                    {
                        "batch_type": "bank_transaction",
                        "source_name": "cost-preview.json",
                        "imported_by": "user_finance_01",
                        "rows": [
                            {
                                "account_no": "62228888",
                                "txn_date": "2026-03-10",
                                "trade_time": "2026-03-10 21:27:55",
                                "counterparty_name": "昆明设备供应商",
                                "debit_amount": "1250.00",
                                "credit_amount": "",
                                "bank_serial_no": "COST-PREVIEW-001",
                            }
                        ],
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        invalidate_all.assert_not_called()
        invalidate_scopes.assert_not_called()

    def test_import_confirm_invalidates_cost_statistics_cache_for_imported_month(self) -> None:
        preview_response = self.app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": "bank_transaction",
                    "source_name": "cost-confirm.json",
                    "imported_by": "user_finance_01",
                    "rows": [
                        {
                            "account_no": "62228888",
                            "txn_date": "2026-03-10",
                            "trade_time": "2026-03-10 21:27:55",
                            "counterparty_name": "昆明设备供应商",
                            "debit_amount": "1250.00",
                            "credit_amount": "",
                            "bank_serial_no": "COST-CONFIRM-001",
                        }
                    ],
                }
            ),
        )
        batch_id = json.loads(preview_response.body)["batch"]["id"]

        with (
            patch.object(self.app, "_invalidate_cost_statistics_read_models") as invalidate_all,
            patch.object(self.app, "_invalidate_cost_statistics_read_model_scopes") as invalidate_scopes,
        ):
            response = self.app.handle_request("POST", "/imports/confirm", json.dumps({"batch_id": batch_id}))

        self.assertEqual(response.status_code, 200)
        invalidate_all.assert_not_called()
        invalidate_scopes.assert_called_once_with(["2026-03"], reason="import_state_changed")

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

    def test_project_scope_defaults_active_allows_all_and_rejects_invalid_scope(self) -> None:
        from fin_ops_platform.domain.enums import BatchType
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        preview = self.app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cost-statistics-project-scope.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 21:27:55",
                    "counterparty_name": "昆明设备供应商",
                    "debit_amount": "1250.00",
                    "credit_amount": "",
                    "bank_serial_no": "COST-SCOPE-001",
                    "summary": "PLC 模块采购",
                    "remark": "设备采购款",
                }
            ],
        )
        self.app._import_service.confirm_import(preview.id)
        settings_payload = self.app._app_settings_service.create_manual_project(
            actor_id="settings_test",
            project_code="LOCAL-COST-001",
            project_name="云南溯源科技",
        )
        completed_project_id = settings_payload["projects"]["active"][0]["id"]
        self.app._app_settings_service.update_settings(
            completed_project_ids=[completed_project_id],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
        )
        self.app._cost_statistics_service = CostStatisticsService(
            self.app._import_service,
            grouped_workbench_loader=self.app._build_api_workbench_payload,
            row_detail_loader=self.app._get_api_workbench_row_detail_payload,
            project_active_checker=self.app._app_settings_service.is_project_active,
        )

        default_payload = json.loads(
            self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03").body
        )
        all_payload = json.loads(
            self.app.handle_request("GET", "/api/cost-statistics/explorer?month=2026-03&project_scope=all").body
        )
        preview_payload = json.loads(
            self.app.handle_request(
                "GET",
                "/api/cost-statistics/export-preview?month=2026-03&view=time&project_scope=all",
            ).body
        )
        invalid_response = self.app.handle_request(
            "GET",
            "/api/cost-statistics/explorer?month=2026-03&project_scope=finished",
        )
        invalid_payload = json.loads(invalid_response.body)

        self.assertEqual(default_payload["summary"]["transaction_count"], 0)
        self.assertEqual(all_payload["summary"]["transaction_count"], 1)
        self.assertEqual(preview_payload["summary"]["transaction_count"], 1)
        self.assertEqual(invalid_response.status_code, 400)
        self.assertEqual(invalid_payload["error"], "invalid_cost_statistics_project_scope")

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
            project_active_checker=app._app_settings_service.is_project_active,
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
