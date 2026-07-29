import unittest
from unittest.mock import patch

from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy


class CostStatisticsPolicyTests(unittest.TestCase):
    def test_bank_flow_follow_up_does_not_build_oa_cost_entries(self) -> None:
        policy = CostStatisticsPolicy(
            {
                "settings": {},
                "bank_rows": [self._bank_row("bank-flow-only")],
                "cost_groups": [self._group()],
                "available_years": ["2026"],
            },
            project_scope="all",
        )

        with patch(
            "fin_ops_platform.services.cost_statistics_policy._cost_entries",
            side_effect=AssertionError("OA cost entries must remain lazy"),
        ):
            page = policy.explorer_page(
                scope_kind="month",
                scope_value="2026-03",
                view="bank_tag",
                filters={},
                cursor_values=None,
                page_size=50,
                include_statistics=False,
            )

        self.assertIsNone(page["statistics"])
        self.assertEqual(page["available_years"], ["2026"])

    def test_explorer_search_filters_rows_summary_and_facets_before_paging(
        self,
    ) -> None:
        policy = CostStatisticsPolicy(
            {
                "settings": {},
                "bank_rows": [
                    {
                        **self._bank_row("bank-match"),
                        "amount": "125.00",
                        "direction": "支出",
                        "counterparty_name": "昆明设备供应商",
                    },
                    {
                        **self._bank_row("bank-other"),
                        "amount": "500.00",
                        "direction": "支出",
                        "counterparty_name": "大理住宿供应商",
                    },
                ],
                "cost_groups": [
                    self._group(
                        group_id="project-match",
                        oa_row=self._oa_row(
                            project_name="项目甲",
                            expense_content="PLC 模块采购",
                        ),
                        bank_rows=[
                            self._bank_row(
                                "cost-match",
                                debit_amount="125.00",
                            )
                        ],
                    ),
                    self._group(
                        group_id="project-other",
                        oa_row=self._oa_row(
                            project_name="项目乙",
                            expense_content="住宿费",
                        ),
                        bank_rows=[
                            self._bank_row(
                                "cost-other",
                                debit_amount="500.00",
                            )
                        ],
                    ),
                ],
            },
            project_scope="all",
        )

        time_page = policy.explorer_page(
            scope_kind="month",
            scope_value="2026-03",
            view="time",
            filters={"query": "昆明设备"},
            cursor_values=None,
            page_size=1,
        )
        project_page = policy.explorer_page(
            scope_kind="month",
            scope_value="2026-03",
            view="project",
            filters={"query": "PLC"},
            cursor_values=None,
            page_size=1,
        )

        self.assertEqual(time_page["summary"]["total_amount"], "125.00")
        self.assertEqual(time_page["row_count"], 1)
        self.assertEqual(time_page["rows"][0]["project_name"], "")
        self.assertEqual(time_page["rows"][0]["expense_type"], "")
        self.assertEqual(
            [row["project_name"] for row in project_page["primary_facets"]],
            ["项目甲"],
        )
        self.assertEqual(project_page["summary"]["total_amount"], "125.00")

    def test_bank_tag_facets_sort_expense_mixed_income_then_zero(self) -> None:
        def tagged_bank(
            row_id: str,
            *,
            label: str,
            amount: str,
            direction: str,
        ) -> dict[str, object]:
            return {
                **self._bank_row(row_id),
                "amount": amount,
                "direction": direction,
                "bank_tag_primary_label": label,
                "bank_tag_sub_label": f"{label}子标签",
            }

        policy = CostStatisticsPolicy(
            {
                "settings": {},
                "bank_rows": [
                    tagged_bank(
                        "expense",
                        label="仅支出",
                        amount="100.00",
                        direction="支出",
                    ),
                    tagged_bank(
                        "mixed-expense",
                        label="收支都有",
                        amount="10.00",
                        direction="支出",
                    ),
                    tagged_bank(
                        "mixed-income",
                        label="收支都有",
                        amount="20.00",
                        direction="收入",
                    ),
                    tagged_bank(
                        "income",
                        label="仅收入",
                        amount="500.00",
                        direction="收入",
                    ),
                    tagged_bank(
                        "zero",
                        label="零金额",
                        amount="0.00",
                        direction="支出",
                    ),
                ],
                "cost_groups": [],
            },
            project_scope="all",
        )

        page = policy.explorer_page(
            scope_kind="month",
            scope_value="2026-03",
            view="bank_tag",
            filters={},
            cursor_values=None,
            page_size=50,
        )

        self.assertEqual(
            [row["primary_label"] for row in page["primary_facets"]],
            ["仅支出", "收支都有", "仅收入", "零金额"],
        )

    def _payload(
        self,
        groups: list[dict[str, object]],
        *,
        project_scope: str = "all",
        settings_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        policy = CostStatisticsPolicy(
            {
                "settings": settings_payload or {},
                "bank_rows": [],
                "cost_groups": groups,
            },
            project_scope=project_scope,
        )
        page = policy.export_page(
            month="2026-03",
            start_month=None,
            end_month=None,
            start_date=None,
            end_date=None,
            project_names=[],
            expense_types=[],
            row_shape="raw_cost",
            offset=0,
            page_size=100,
            include_summary=True,
        )
        return {
            "summary": {
                key: page["summary"][key]
                for key in ("row_count", "transaction_count", "total_amount")
            },
            "time_rows": list(page["rows"]),
        }

    def test_projection_counts_only_outflow_with_one_complete_oa_context(self) -> None:
        group = self._group(
            oa_row={
                "project_name": "云南溯源科技",
                "expense_type": "--",
                "expense_content": "—",
                "detail_fields": {
                    "项目编号": "P-001",
                    "费用类型": "交通费",
                    "费用内容": "项目现场往返交通",
                    "申请人": "刘际涛",
                },
            },
            bank_rows=[
                self._bank_row("txn-out", debit_amount="1,000.00"),
                self._bank_row("txn-income", debit_amount="", credit_amount="888.00"),
            ],
        )

        payload = self._payload([group])

        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "1,000.00")
        self.assertEqual(payload["time_rows"][0]["project_id"], "P-001")
        self.assertEqual(payload["time_rows"][0]["expense_type"], "交通费")
        self.assertEqual(payload["time_rows"][0]["expense_content"], "项目现场往返交通")
        self.assertEqual(payload["time_rows"][0]["oa_applicant"], "刘际涛")

    def test_projection_excludes_in_progress_oa_and_uses_only_completed_contexts(self) -> None:
        only_in_progress = self._group(
            group_id="in-progress-only",
            oa_row=self._oa_row(workflow_status="in_progress"),
        )
        mixed = self._group(
            group_id="mixed-status",
            oa_rows=[
                self._oa_row(
                    id="oa-completed",
                    workflow_status="completed",
                    project_name="已完成项目",
                    expense_type="材料费",
                ),
                self._oa_row(
                    id="oa-in-progress",
                    workflow_status="in_progress",
                    project_name="进行中项目",
                    expense_type="劳务费",
                ),
            ],
        )

        payload = self._payload([only_in_progress, mixed])

        self.assertEqual(payload["summary"], {"row_count": 1, "transaction_count": 1, "total_amount": "1,000.00"})
        self.assertEqual(payload["time_rows"][0]["group_id"], "mixed-status")
        self.assertEqual(payload["time_rows"][0]["project_name"], "已完成项目")
        self.assertEqual(payload["time_rows"][0]["expense_type"], "材料费")

    def test_projection_ignores_legacy_oa_exclusion_markers(self) -> None:
        legacy_exclusion_fields = (
            {"cost_excluded": True},
            {"tags": ["冲"]},
            {"oa_bank_relation": {"code": "oa_invoice_offset_auto_match"}},
        )
        for index, excluded in enumerate(legacy_exclusion_fields):
            with self.subTest(excluded=excluded):
                group = self._group(
                    group_id=f"excluded-{index}",
                    oa_row={
                        "project_name": "云南溯源科技",
                        "expense_type": "交通费",
                        "expense_content": "汽油费冲账",
                        **excluded,
                    },
                )
                payload = self._payload([group])
                self.assertEqual(payload["summary"]["transaction_count"], 1)
                self.assertEqual(payload["summary"]["total_amount"], "1,000.00")

    def test_projection_keeps_loan_incomplete_and_conflicting_oa_contexts(self) -> None:
        cases = (
            [self._oa_row(expense_type="借款")],
            [self._oa_row(expense_content="")],
            [self._oa_row(), self._oa_row(project_name="另一个项目")],
        )
        for index, oa_rows in enumerate(cases):
            with self.subTest(index=index):
                payload = self._payload([self._group(group_id=f"invalid-{index}", oa_rows=oa_rows)])
                self.assertEqual(payload["summary"]["transaction_count"], 1)
        loan = self._payload([self._group(oa_rows=cases[0])])["time_rows"][0]
        incomplete = self._payload([self._group(oa_rows=cases[1])])["time_rows"][0]
        conflicting = self._payload([self._group(oa_rows=cases[2])])["time_rows"][0]
        self.assertEqual(loan["expense_type"], "借款")
        self.assertEqual(incomplete["expense_content"], "交通费")
        self.assertEqual(conflicting["project_name"], "未归集项目")

    def test_projection_ignores_legacy_special_exclusion_policy(self) -> None:
        hint = self._group(
            group_id="cash-hint",
            special_metadata={
                "special_type": "cash_turnover_detected",
                "cost_policy": "hint_only",
                "cost_excluded": False,
            },
        )
        excluded = self._group(
            group_id="cash-pass-through",
            special_metadata={
                "special_type": "cash_pass_through",
                "cost_policy": "exclude_all",
                "cash_amount": "1,000.00",
            },
        )

        payload = self._payload([hint, excluded])

        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["summary"]["total_amount"], "2,000.00")
        self.assertEqual(
            {row["group_id"] for row in payload["time_rows"]},
            {"cash-hint", "cash-pass-through"},
        )

    def test_projection_uses_only_confirmed_ticket_cost(self) -> None:
        group = self._group(
            group_id="cash-ticket",
            special_metadata={
                "special_type": "cash_ticket_purchase",
                "cost_policy": "include_ticket_cost_only",
                "cash_amount": "1,000.00",
                "ticket_cost_amount": "120.00",
                "project_name": "买票项目",
                "expense_type": "现金往来",
                "expense_content": "买票成本",
            },
        )

        payload = self._payload([group])

        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "120.00")
        self.assertEqual(payload["time_rows"][0]["project_name"], "买票项目")
        self.assertEqual(payload["time_rows"][0]["expense_type"], "现金往来")
        self.assertEqual(payload["time_rows"][0]["expense_content"], "买票成本")

    def test_projection_excludes_ticket_cost_when_oa_is_in_progress(self) -> None:
        group = self._group(
            group_id="cash-ticket-in-progress",
            oa_row=self._oa_row(workflow_status="in_progress"),
            special_metadata={
                "special_type": "cash_ticket_purchase",
                "ticket_cost_amount": "120.00",
            },
        )

        payload = self._payload([group])

        self.assertEqual(
            payload["summary"],
            {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
        )

    def test_projection_ignores_invoice_member_metadata(self) -> None:
        group = self._group(group_id="invoice-metadata")
        group["invoice_rows"] = [
            {
                "id": "invoice-1",
                "type": "invoice",
                "special_metadata": {
                    "special_type": "cash_ticket_purchase",
                    "ticket_cost_amount": "120.00",
                },
            }
        ]

        payload = self._payload([group])

        self.assertEqual(
            payload["summary"],
            {"row_count": 1, "transaction_count": 1, "total_amount": "1,000.00"},
        )

    def test_projection_does_not_let_member_exclude_all_override_oa_pair(self) -> None:
        group = self._group(group_id="member-policy")
        group["oa_rows"][0]["special_metadata"] = {"cost_policy": "exclude_all"}

        payload = self._payload([group])

        self.assertEqual(payload["summary"]["transaction_count"], 1)

    def test_projection_splits_one_bank_by_exact_multi_oa_amounts(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(id="oa-a", project_name="项目A", expense_type="材料费", amount="60.00"),
                self._oa_row(id="oa-b", project_name="项目B", expense_type="劳务费", amount="40.00"),
            ],
            bank_rows=[self._bank_row("bank-split", debit_amount="100.00")],
        )

        payload = self._payload([group])

        self.assertEqual(payload["summary"], {"row_count": 2, "transaction_count": 1, "total_amount": "100.00"})
        self.assertEqual(
            {(row["row_key"], row["project_name"], row["expense_type"], row["amount"]) for row in payload["time_rows"]},
            {
                ("bank-split:oa:oa-a", "项目A", "材料费", "60.00"),
                ("bank-split:oa:oa-b", "项目B", "劳务费", "40.00"),
            },
        )
        self.assertEqual(
            {row["transaction_id"] for row in payload["time_rows"]},
            {"bank-split"},
        )

    def test_payment_applications_keep_one_row_when_dimensions_are_equal(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(id="oa-a", amount="60.00"),
                self._oa_row(id="oa-b", amount="40.00"),
            ],
            bank_rows=[self._bank_row("bank-payment", debit_amount="100.00")],
        )

        payload = self._payload([group])

        self.assertEqual(
            payload["summary"],
            {"row_count": 1, "transaction_count": 1, "total_amount": "100.00"},
        )
        self.assertEqual(payload["time_rows"][0]["row_key"], "bank-payment:full")

    def test_projection_does_not_infer_split_when_amounts_mismatch(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(id="oa-a", project_name="项目A", expense_type="材料费", amount="60.00"),
                self._oa_row(id="oa-b", project_name="项目B", expense_type="劳务费", amount="30.00"),
            ],
            bank_rows=[self._bank_row("bank-full", debit_amount="100.00")],
        )

        payload = self._payload([group])

        self.assertEqual(payload["summary"], {"row_count": 1, "transaction_count": 1, "total_amount": "100.00"})
        self.assertEqual(payload["time_rows"][0]["row_key"], "bank-full:full")
        self.assertEqual(payload["time_rows"][0]["project_name"], "未归集项目")
        self.assertEqual(payload["time_rows"][0]["expense_type"], "未分类")

    def test_projection_does_not_split_multiple_bank_rows(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(id="oa-a", project_name="项目A", amount="60.00"),
                self._oa_row(id="oa-b", project_name="项目B", amount="40.00"),
            ],
            bank_rows=[
                self._bank_row("bank-a", debit_amount="60.00"),
                self._bank_row("bank-b", debit_amount="40.00"),
            ],
        )

        payload = self._payload([group])

        self.assertEqual(payload["summary"], {"row_count": 2, "transaction_count": 2, "total_amount": "100.00"})
        self.assertEqual({row["project_name"] for row in payload["time_rows"]}, {"未归集项目"})
        self.assertEqual({row["row_key"] for row in payload["time_rows"]}, {"bank-a:full", "bank-b:full"})

    def test_daily_reimbursement_splits_by_canonical_expense_items(self) -> None:
        group = self._group(
            oa_row=self._oa_row(
                id="oa-daily",
                apply_type="日常报销",
                project_name="项目A；项目B",
                expense_type="交通费；住宿费",
                amount="100.00",
                expense_items=[
                    {
                        "expense_item_id": "item-1",
                        "project_id": "P-A",
                        "project_name": "项目A",
                        "expense_type": "交通费",
                        "expense_content": "市内交通",
                        "amount": "40.00",
                    },
                    {
                        "expense_item_id": "item-2",
                        "project_id": "P-B",
                        "project_name": "项目B",
                        "expense_type": "住宿费",
                        "expense_content": "出差住宿",
                        "amount": "60.00",
                    },
                ],
            ),
            bank_rows=[self._bank_row("bank-daily", debit_amount="100.00")],
        )

        payload = self._payload([group])

        self.assertEqual(
            payload["summary"],
            {"row_count": 2, "transaction_count": 1, "total_amount": "100.00"},
        )
        self.assertEqual(
            {
                (
                    row["row_key"],
                    row["project_name"],
                    row["expense_type"],
                    row["amount"],
                )
                for row in payload["time_rows"]
            },
            {
                (
                    "bank-daily:oa:oa-daily:item:item-1",
                    "项目A",
                    "交通费",
                    "40.00",
                ),
                (
                    "bank-daily:oa:oa-daily:item:item-2",
                    "项目B",
                    "住宿费",
                    "60.00",
                ),
            },
        )

    def test_daily_reimbursements_and_payment_application_share_exact_split(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(
                    id="oa-daily",
                    apply_type="日常报销",
                    amount="30.00",
                    expense_items=[
                        {
                            "expense_item_id": "item-1",
                            "project_name": "项目A",
                            "expense_type": "交通费",
                            "amount": "30.00",
                        }
                    ],
                ),
                self._oa_row(
                    id="oa-payment",
                    apply_type="支付申请",
                    project_name="项目B",
                    expense_type="材料费",
                    amount="70.00",
                ),
            ],
            bank_rows=[self._bank_row("bank-mixed", debit_amount="100.00")],
        )

        payload = self._payload([group])

        self.assertEqual(
            {
                (row["project_name"], row["amount"])
                for row in payload["time_rows"]
            },
            {("项目A", "30.00"), ("项目B", "70.00")},
        )
        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "100.00")

    def test_multiple_daily_reimbursements_split_one_bank_by_each_item(self) -> None:
        group = self._group(
            oa_rows=[
                self._oa_row(
                    id="oa-daily-a",
                    apply_type="日常报销",
                    amount="30.00",
                    expense_items=[
                        {
                            "expense_item_id": "item-a",
                            "project_name": "项目A",
                            "expense_type": "交通费",
                            "amount": "30.00",
                        }
                    ],
                ),
                self._oa_row(
                    id="oa-daily-b",
                    apply_type="日常报销",
                    amount="70.00",
                    expense_items=[
                        {
                            "expense_item_id": "item-b",
                            "project_name": "项目B",
                            "expense_type": "材料费",
                            "amount": "70.00",
                        }
                    ],
                ),
            ],
            bank_rows=[self._bank_row("bank-two-daily", debit_amount="100.00")],
        )
        policy = CostStatisticsPolicy(
            {
                "settings": {},
                "bank_rows": [],
                "cost_groups": [group],
            },
            project_scope="all",
        )

        detail = policy.transaction(
            transaction_id="bank-two-daily",
            bank_flow_view=False,
            scope_kind="month",
            scope_value="2026-03",
        )

        self.assertIsNotNone(detail)
        self.assertEqual(detail["linked_oa_count"], 2)
        self.assertEqual(len(detail["cost_allocations"]), 2)
        self.assertEqual(
            {
                (row["project_name"], row["amount"])
                for row in detail["cost_allocations"]
            },
            {("项目A", "30.00"), ("项目B", "70.00")},
        )

    def test_daily_reimbursement_invalid_items_fail_closed(self) -> None:
        cases = {
            "duplicate_id": ("duplicate", "duplicate", "40.00", "60.00"),
            "missing_id": ("", "item-2", "40.00", "60.00"),
            "zero_amount": ("item-1", "item-2", "0.00", "100.00"),
            "negative_amount": ("item-1", "item-2", "-1.00", "101.00"),
            "amount_mismatch": ("item-1", "item-2", "40.00", "50.00"),
        }
        for name, (first_id, second_id, first_amount, second_amount) in cases.items():
            with self.subTest(name=name):
                group = self._group(
                    oa_row=self._oa_row(
                        id=f"oa-invalid-{name}",
                        apply_type="日常报销",
                        amount="100.00",
                        expense_items=[
                            {
                                "expense_item_id": first_id,
                                "project_name": "项目A",
                                "expense_type": "交通费",
                                "amount": first_amount,
                            },
                            {
                                "expense_item_id": second_id,
                                "project_name": "项目B",
                                "expense_type": "住宿费",
                                "amount": second_amount,
                            },
                        ],
                    ),
                    bank_rows=[
                        self._bank_row(
                            f"bank-invalid-{name}",
                            debit_amount="100.00",
                        )
                    ],
                )

                payload = self._payload([group])

                self.assertEqual(
                    payload["summary"],
                    {
                        "row_count": 1,
                        "transaction_count": 1,
                        "total_amount": "100.00",
                    },
                )
                self.assertEqual(
                    payload["time_rows"][0]["project_name"],
                    "未归集项目",
                )
                self.assertEqual(
                    payload["time_rows"][0]["expense_type"],
                    "未分类",
                )

    def test_legacy_ambiguous_dimension_labels_never_escape_cost_policy(self) -> None:
        payload = self._payload(
            [
                self._group(
                    oa_row=self._oa_row(
                        project_name="多项目",
                        expense_type="多费用类型",
                    )
                )
            ]
        )

        self.assertEqual(
            payload["time_rows"][0]["project_name"],
            "未归集项目",
        )
        self.assertEqual(
            payload["time_rows"][0]["expense_type"],
            "未分类",
        )

    def test_active_scope_filters_daily_reimbursement_items_individually(self) -> None:
        group = self._group(
            oa_row=self._oa_row(
                id="oa-scope",
                apply_type="日常报销",
                amount="100.00",
                expense_items=[
                    {
                        "expense_item_id": "item-active",
                        "project_id": "P-ACTIVE",
                        "project_name": "进行中项目",
                        "expense_type": "交通费",
                        "amount": "40.00",
                    },
                    {
                        "expense_item_id": "item-done",
                        "project_id": "P-DONE",
                        "project_name": "已完成项目",
                        "expense_type": "住宿费",
                        "amount": "60.00",
                    },
                ],
            ),
            bank_rows=[self._bank_row("bank-scope", debit_amount="100.00")],
        )
        settings = {
            "projects": {
                "completed": [
                    {"id": "P-DONE", "project_name": "已完成项目"}
                ],
                "completed_project_ids": ["P-DONE"],
            }
        }

        active_payload = self._payload(
            [group],
            project_scope="active",
            settings_payload=settings,
        )
        all_payload = self._payload(
            [group],
            project_scope="all",
            settings_payload=settings,
        )

        self.assertEqual(active_payload["summary"]["total_amount"], "40.00")
        self.assertEqual(
            {row["project_name"] for row in active_payload["time_rows"]},
            {"进行中项目"},
        )
        self.assertEqual(all_payload["summary"]["total_amount"], "100.00")

    def test_projection_owns_cross_month_relation_by_native_bank_month(self) -> None:
        payload = self._payload(
            [
                self._group(
                    bank_rows=[
                        {
                            **self._bank_row("bank-feb", debit_amount="100.00"),
                            "trade_time": "2026-02-28 23:59:59",
                        }
                    ]
                )
            ]
        )

        self.assertEqual(payload["summary"], {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"})
        self.assertEqual(payload["time_rows"], [])

    def test_active_scope_excludes_only_known_completed_projects(self) -> None:
        groups = [
            self._group(group_id="completed-id", oa_row=self._oa_row(project_id="P-DONE-ID")),
            self._group(group_id="completed-name", oa_row=self._oa_row(project_name="已完成项目")),
            self._group(group_id="active", oa_row=self._oa_row(project_name="进行中项目")),
            self._group(group_id="unknown", oa_row=self._oa_row(project_name="未登记项目")),
        ]
        settings = {
            "projects": {
                "active": [{"id": "P-ACTIVE", "project_name": "进行中项目"}],
                "completed": [{"id": "P-DONE-NAME", "project_name": "已完成项目"}],
                "completed_project_ids": ["P-DONE-ID", "P-DONE-NAME"],
            }
        }

        active_payload = self._payload(groups, project_scope="active", settings_payload=settings)
        all_payload = self._payload(groups, project_scope="all", settings_payload=settings)

        self.assertEqual(
            {row["project_name"] for row in active_payload["time_rows"]},
            {"进行中项目", "未登记项目"},
        )
        self.assertEqual(all_payload["summary"]["transaction_count"], 4)

    def test_public_rebuild_rejects_invalid_project_scope(self) -> None:
        with self.assertRaisesRegex(ValueError, "project_scope must be active or all"):
            CostStatisticsPolicy({}, project_scope="finished")

    @staticmethod
    def _oa_row(**overrides: object) -> dict[str, object]:
        return {
            "id": "oa-cost",
            "type": "oa",
            "project_id": "P-001",
            "project_name": "云南溯源科技",
            "expense_type": "交通费",
            "expense_content": "项目现场交通",
            "applicant": "刘际涛",
            **overrides,
        }

    @staticmethod
    def _bank_row(
        row_id: str,
        *,
        debit_amount: str = "1,000.00",
        credit_amount: str = "",
    ) -> dict[str, object]:
        return {
            "id": row_id,
            "type": "bank",
            "trade_time": "2026-03-10 21:27:55",
            "debit_amount": debit_amount,
            "credit_amount": credit_amount,
            "counterparty_name": "昆明设备供应商",
            "payment_account_label": "工商银行 账户 0001",
            "remark": "项目费用",
        }

    @classmethod
    def _group(
        cls,
        *,
        group_id: str = "group-cost",
        oa_row: dict[str, object] | None = None,
        oa_rows: list[dict[str, object]] | None = None,
        bank_rows: list[dict[str, object]] | None = None,
        special_metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "group_id": group_id,
            "group_type": "manual_confirmed",
            "special_metadata": dict(special_metadata or {}),
            "oa_rows": list(oa_rows if oa_rows is not None else [oa_row or cls._oa_row()]),
            "bank_rows": list(bank_rows if bank_rows is not None else [cls._bank_row(f"txn-{group_id}")]),
            "invoice_rows": [],
        }


if __name__ == "__main__":
    unittest.main()
