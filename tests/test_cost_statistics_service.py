from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService


class CostStatisticsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        existing_transactions = [
            BankTransaction(
                id="txn-cost-001",
                account_no="62220001",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="昆明设备供应商",
                amount=Decimal("1000.00"),
                signed_amount=Decimal("-1000.00"),
                txn_date="2026-03-10",
                trade_time="2026-03-10 21:27:55",
                pay_receive_time="2026-03-10 21:27:55",
                summary="设备采购",
                remark="设备采购款",
            ),
            BankTransaction(
                id="txn-cost-002",
                account_no="62220002",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="昆明设备供应商",
                amount=Decimal("250.00"),
                signed_amount=Decimal("-250.00"),
                txn_date="2026-03-11",
                trade_time="2026-03-11 09:01:02",
                pay_receive_time="2026-03-11 09:01:02",
                summary="设备采购",
                remark="设备配件款",
            ),
            BankTransaction(
                id="txn-cost-003",
                account_no="62220003",
                txn_direction=TransactionDirection.INFLOW,
                counterparty_name_raw="客户回款",
                amount=Decimal("888.00"),
                signed_amount=Decimal("888.00"),
                txn_date="2026-03-12",
                trade_time="2026-03-12 10:11:12",
                pay_receive_time="2026-03-12 10:11:12",
                summary="客户回款",
            ),
        ]
        self.import_service = ImportNormalizationService(existing_transactions=existing_transactions)
        self.grouped_payloads = {
            "2026-03": {
                "month": "2026-03",
                "summary": {},
                "paired": {
                    "groups": [
                        {
                            "group_id": "group-cost-001",
                            "group_type": "manual_confirmed",
                            "match_confidence": "high",
                            "reason": "confirmed",
                            "oa_rows": [
                                {
                                    "id": "oa-cost-001",
                                    "type": "oa",
                                    "project_name": "云南溯源科技",
                                    "expense_type": "设备货款及材料费",
                                    "expense_content": "PLC 模块采购",
                                    "amount": "1250.00",
                                }
                            ],
                            "bank_rows": [
                                {
                                    "id": "txn-cost-001",
                                    "type": "bank",
                                    "trade_time": "2026-03-10 21:27:55",
                                    "debit_amount": "1,000.00",
                                    "credit_amount": "",
                                    "counterparty_name": "昆明设备供应商",
                                    "payment_account_label": "工商银行 账户 0001",
                                    "remark": "设备采购款",
                                },
                                {
                                    "id": "txn-cost-002",
                                    "type": "bank",
                                    "trade_time": "2026-03-11 09:01:02",
                                    "debit_amount": "250.00",
                                    "credit_amount": "",
                                    "counterparty_name": "昆明设备供应商",
                                    "payment_account_label": "工商银行 账户 0002",
                                    "remark": "设备配件款",
                                },
                            ],
                            "invoice_rows": [],
                        },
                        {
                            "group_id": "group-cost-002",
                            "group_type": "manual_confirmed",
                            "match_confidence": "high",
                            "reason": "confirmed",
                            "oa_rows": [
                                {
                                    "id": "oa-cost-002",
                                    "type": "oa",
                                    "project_name": "云南溯源科技",
                                    "expense_type": "",
                                    "expense_content": "未填写费用类型",
                                    "amount": "300.00",
                                }
                            ],
                            "bank_rows": [
                                {
                                    "id": "txn-cost-003",
                                    "type": "bank",
                                    "trade_time": "2026-03-12 10:11:12",
                                    "debit_amount": "",
                                    "credit_amount": "888.00",
                                    "counterparty_name": "客户回款",
                                    "payment_account_label": "工商银行 账户 0003",
                                    "remark": "收入流水",
                                }
                            ],
                            "invoice_rows": [],
                        },
                    ]
                },
                "open": {"groups": []},
            }
        }
        self.row_details = {
            "txn-cost-001": {
                "id": "txn-cost-001",
                "type": "bank",
                "summary_fields": {"交易时间": "2026-03-10 21:27:55"},
                "detail_fields": {
                    "账号": "62220001",
                    "账户名称": "云南溯源科技有限公司",
                    "摘要": "设备采购",
                    "备注": "设备采购款",
                },
            },
            "txn-cost-002": {
                "id": "txn-cost-002",
                "type": "bank",
                "summary_fields": {"交易时间": "2026-03-11 09:01:02"},
                "detail_fields": {
                    "账号": "62220002",
                    "账户名称": "云南溯源科技有限公司",
                    "摘要": "设备采购",
                    "备注": "设备配件款",
                },
            },
        }

    def test_month_statistics_only_counts_outflow_rows_with_complete_oa_cost_fields(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_month_statistics("2026-03")

        self.assertEqual(payload["month"], "2026-03")
        self.assertEqual(payload["summary"]["row_count"], 1)
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["summary"]["total_amount"], "1,250.00")
        self.assertEqual(payload["rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(payload["rows"][0]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["rows"][0]["expense_content"], "PLC 模块采购")
        self.assertEqual(payload["rows"][0]["amount"], "1,250.00")

    def test_project_statistics_returns_time_amount_and_expense_fields(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_project_statistics("2026-03", "云南溯源科技")

        self.assertEqual(payload["project_name"], "云南溯源科技")
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["summary"]["total_amount"], "1,250.00")
        self.assertEqual(payload["rows"][0]["trade_time"], "2026-03-10 21:27:55")
        self.assertEqual(payload["rows"][0]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["rows"][0]["expense_content"], "PLC 模块采购")
        self.assertEqual(payload["rows"][0]["amount"], "1,000.00")

    def test_explorer_all_aggregates_entries_across_multiple_months(self) -> None:
        from fin_ops_platform.domain.models import BankTransaction
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        april_transaction = BankTransaction(
            id="txn-cost-101",
            account_no="62220004",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="云南冶金集团股份有限公司",
            amount=Decimal("4800.00"),
            signed_amount=Decimal("-4800.00"),
            txn_date="2026-04-02",
            trade_time="2026-04-02 09:15:08",
            pay_receive_time="2026-04-02 09:15:08",
            summary="项目办公室租赁",
            remark="办公室租赁费",
        )
        import_service = ImportNormalizationService(
            existing_transactions=[*self.import_service.list_transactions(), april_transaction]
        )
        grouped_payloads = dict(self.grouped_payloads)
        grouped_payloads["2026-04"] = {
            "month": "2026-04",
            "summary": {},
            "paired": {
                "groups": [
                    {
                        "group_id": "group-cost-101",
                        "group_type": "manual_confirmed",
                        "match_confidence": "high",
                        "reason": "confirmed",
                        "oa_rows": [
                            {
                                "id": "oa-cost-101",
                                "type": "oa",
                                "project_name": "昆明卷烟厂动力设备控制系统升级改造项目",
                                "expense_type": "经营/办公费用",
                                "expense_content": "项目办公室租赁",
                                "amount": "4800.00",
                            }
                        ],
                        "bank_rows": [
                            {
                                "id": "txn-cost-101",
                                "type": "bank",
                                "trade_time": "2026-04-02 09:15:08",
                                "debit_amount": "4,800.00",
                                "credit_amount": "",
                                "counterparty_name": "云南冶金集团股份有限公司",
                                "payment_account_label": "平安银行 账户 8821",
                                "remark": "办公室租赁费",
                            }
                        ],
                        "invoice_rows": [],
                    }
                ]
            },
            "open": {"groups": []},
        }
        service = CostStatisticsService(
            import_service,
            grouped_workbench_loader=lambda month: grouped_payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_explorer("all")

        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["summary"]["transaction_count"], 3)
        self.assertEqual(payload["summary"]["total_amount"], "6,050.00")
        self.assertEqual(payload["project_rows"][0]["project_name"], "昆明卷烟厂动力设备控制系统升级改造项目")
        self.assertEqual(payload["project_rows"][1]["project_name"], "云南溯源科技")

    def test_transaction_detail_includes_bank_and_oa_cost_fields(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_transaction_detail("txn-cost-001")

        self.assertEqual(payload["transaction"]["id"], "txn-cost-001")
        self.assertEqual(payload["transaction"]["project_name"], "云南溯源科技")
        self.assertEqual(payload["transaction"]["expense_type"], "设备货款及材料费")
        self.assertEqual(payload["transaction"]["expense_content"], "PLC 模块采购")
        self.assertEqual(payload["transaction"]["amount"], "1,000.00")
        self.assertIn("detail_fields", payload["transaction"])

    def test_group_cost_context_treats_dash_placeholders_as_empty_and_falls_back_to_detail_fields(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        payloads = {
            "2026-03": {
                "month": "2026-03",
                "summary": {},
                "paired": {
                    "groups": [
                        {
                            "group_id": "group-cost-003",
                            "group_type": "manual_confirmed",
                            "match_confidence": "high",
                            "reason": "confirmed",
                            "oa_rows": [
                                {
                                    "id": "oa-cost-003",
                                    "type": "oa",
                                    "project_name": "云南溯源科技",
                                    "expense_type": "-",
                                    "expense_content": "--",
                                    "amount": "1000.00",
                                    "detail_fields": {
                                        "费用类型": "交通费",
                                        "费用内容": "项目现场往返交通",
                                    },
                                }
                            ],
                            "bank_rows": [
                                {
                                    "id": "txn-cost-001",
                                    "type": "bank",
                                    "trade_time": "2026-03-10 21:27:55",
                                    "debit_amount": "1,000.00",
                                    "credit_amount": "",
                                    "counterparty_name": "昆明设备供应商",
                                    "payment_account_label": "工商银行 账户 0001",
                                    "remark": "设备采购款",
                                }
                            ],
                            "invoice_rows": [],
                        }
                    ]
                },
                "open": {"groups": []},
            }
        }

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_explorer("2026-03")

        self.assertEqual(payload["time_rows"][0]["expense_type"], "交通费")
        self.assertEqual(payload["time_rows"][0]["expense_content"], "项目现场往返交通")

    def test_cost_entries_skip_oa_invoice_offset_groups(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        payloads = {
            "2026-03": {
                "month": "2026-03",
                "summary": {},
                "paired": {
                    "groups": [
                        {
                            "group_id": "case:offset-001",
                            "group_type": "auto_closed",
                            "match_confidence": "high",
                            "reason": "oa_invoice_offset_auto_match",
                            "oa_rows": [
                                {
                                    "id": "oa-offset-001",
                                    "type": "oa",
                                    "project_name": "云南溯源科技",
                                    "expense_type": "交通费",
                                    "expense_content": "汽油费冲账",
                                    "amount": "200.00",
                                    "cost_excluded": True,
                                    "tags": ["冲"],
                                }
                            ],
                            "bank_rows": [
                                {
                                    "id": "txn-cost-001",
                                    "type": "bank",
                                    "trade_time": "2026-03-10 21:27:55",
                                    "debit_amount": "1,000.00",
                                    "credit_amount": "",
                                    "counterparty_name": "昆明设备供应商",
                                    "payment_account_label": "工商银行 账户 0001",
                                    "remark": "设备采购款",
                                }
                            ],
                            "invoice_rows": [],
                        }
                    ]
                },
                "open": {"groups": []},
            }
        }
        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_explorer("2026-03")

        self.assertEqual(payload["summary"]["transaction_count"], 0)
        self.assertEqual(payload["summary"]["total_amount"], "0.00")

    def test_project_scope_filters_completed_projects_by_name_and_keeps_unknown_projects_active(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        payloads = {
            "2026-03": {
                "month": "2026-03",
                "summary": {},
                "paired": {
                    "groups": [
                        self._project_scope_group(
                            group_id="group-active-project",
                            bank_id="txn-scope-active",
                            project_name="进行中项目",
                            amount="100.00",
                        ),
                        self._project_scope_group(
                            group_id="group-completed-project",
                            bank_id="txn-scope-completed",
                            project_name="已完成项目",
                            amount="200.00",
                        ),
                        self._project_scope_group(
                            group_id="group-unknown-project",
                            bank_id="txn-scope-unknown",
                            project_name="未登记项目",
                            amount="300.00",
                        ),
                    ]
                },
                "open": {"groups": []},
            }
        }
        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
            project_active_checker=lambda project_id, project_name: project_name != "已完成项目",
        )

        active_payload = service.get_explorer("2026-03")
        all_payload = service.get_explorer("2026-03", project_scope="all")
        preview_payload = service.get_export_preview(month="2026-03", view="time")

        self.assertEqual(active_payload["summary"]["transaction_count"], 2)
        self.assertEqual(active_payload["summary"]["total_amount"], "400.00")
        self.assertEqual(
            {row["project_name"] for row in active_payload["time_rows"]},
            {"进行中项目", "未登记项目"},
        )
        self.assertEqual(all_payload["summary"]["transaction_count"], 3)
        self.assertEqual(all_payload["summary"]["total_amount"], "600.00")
        self.assertEqual(preview_payload["summary"]["transaction_count"], 2)

    def test_open_attached_unique_candidate_groups_are_included_in_cost_statistics(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        payloads = {
            "2026-03": {
                "month": "2026-03",
                "summary": {},
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "group-open-linked-cost",
                            "group_type": "candidate",
                            "match_confidence": "medium",
                            "reason": "attached_unique_candidate",
                            "oa_rows": [
                                {
                                    "id": "oa-open-cost-001",
                                    "type": "oa",
                                    "project_name": "云南溯源科技",
                                    "expense_type": "交通费",
                                    "expense_content": "项目现场交通",
                                    "oa_bank_relation": {
                                        "code": "pending_match",
                                        "label": "待找流水与发票",
                                        "tone": "warn",
                                    },
                                }
                            ],
                            "bank_rows": [
                                {
                                    "id": "txn-cost-001",
                                    "type": "bank",
                                    "trade_time": "2026-03-10 21:27:55",
                                    "debit_amount": "1,000.00",
                                    "credit_amount": "",
                                    "counterparty_name": "昆明设备供应商",
                                    "payment_account_label": "工商银行 账户 0001",
                                    "remark": "设备采购款",
                                    "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"],
                                }
                            ],
                            "invoice_rows": [],
                        }
                    ]
                },
            }
        }

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        payload = service.get_explorer("2026-03", project_scope="all")

        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "1,000.00")
        self.assertEqual(payload["time_rows"][0]["project_name"], "云南溯源科技")
        self.assertEqual(payload["time_rows"][0]["expense_type"], "交通费")

    def test_invalid_project_scope_is_rejected(self) -> None:
        from fin_ops_platform.services.cost_statistics_service import CostStatisticsService

        service = CostStatisticsService(
            self.import_service,
            grouped_workbench_loader=lambda month: self.grouped_payloads[month],
            row_detail_loader=lambda row_id: self.row_details[row_id],
        )

        with self.assertRaisesRegex(ValueError, "project_scope must be active or all"):
            service.get_explorer("2026-03", project_scope="finished")

    @staticmethod
    def _project_scope_group(
        *,
        group_id: str,
        bank_id: str,
        project_name: str,
        amount: str,
    ) -> dict[str, object]:
        return {
            "group_id": group_id,
            "group_type": "manual_confirmed",
            "match_confidence": "high",
            "reason": "confirmed",
            "oa_rows": [
                {
                    "id": f"oa-{bank_id}",
                    "type": "oa",
                    "project_name": project_name,
                    "expense_type": "交通费",
                    "expense_content": "项目现场交通",
                    "amount": amount,
                }
            ],
            "bank_rows": [
                {
                    "id": bank_id,
                    "type": "bank",
                    "trade_time": "2026-03-10 21:27:55",
                    "debit_amount": amount,
                    "credit_amount": "",
                    "counterparty_name": "昆明设备供应商",
                    "payment_account_label": "工商银行 账户 0001",
                    "remark": "项目费用",
                }
            ],
            "invoice_rows": [],
        }


if __name__ == "__main__":
    unittest.main()
