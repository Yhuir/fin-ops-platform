from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.services.cost_statistics_policy import (
    CostStatisticsAllocationConflictError,
    CostStatisticsPolicy,
)


class CostStatisticsPolicyTests(unittest.TestCase):
    def test_daily_reimbursement_allocates_relation_net_cost_by_oa_weight_and_bank_date(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa(
                            "oa-exp-1",
                            apply_type="日常报销",
                            completed_at="2026-07-23 18:00:00",
                            amount="1015.00",
                            expense_items=[
                                self._item("item-1", "玉溪项目", "住宿费", "240.00"),
                                self._item("item-2", "大理卷烟厂余热综合利用项目", "住宿费", "710.00"),
                                self._item("item-3", "曲靖项目", "邮寄费", "65.00"),
                            ],
                        )
                    ],
                    bank_rows=[
                        self._bank("bank-1050", "1050.00", trade_time="2026-08-01 15:58:31"),
                        self._bank(
                            "bank-refund-35",
                            "35.00",
                            direction="inflow",
                            tag_code="refund-code",
                            tag_label="付错退款",
                            trade_time="2026-08-01 16:22:04",
                        ),
                    ],
                )
            ]
        )

        rows = policy.serialized_cost_rows
        self.assertEqual({row["amount"] for row in rows}, {"240.00", "710.00", "65.00"})
        self.assertEqual({row["transaction_id"] for row in rows}, {"bank-1050"})
        dali = next(row for row in rows if row["project_name"] == "大理卷烟厂余热综合利用项目")
        self.assertEqual(dali["month"], "2026-08")
        self.assertEqual(dali["oa_completed_at"], "2026-07-23 18:00:00")
        self.assertEqual(dali["payment_account_label"], "建设银行 8106")
        detail = policy.allocation(
            allocation_id="bank:bank-1050:oa:oa-exp-1:item:item-2",
            scope_kind="month",
            scope_value="2026-08",
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["amount"], "710.00")
        self.assertEqual(detail["oa_original_amount"], "710.00")
        self.assertEqual(detail["oa_allocation_weight"], "69.95%")
        self.assertEqual(detail["bank_event_amount"], "1050.00")
        self.assertEqual(detail["reconciliation"]["paid_wrong_refund_total"], "35.00")
        self.assertEqual(detail["reconciliation"]["net_cash_cost"], "1015.00")
        self.assertEqual(detail["reconciliation"]["difference"], "0.00")
        self.assertEqual(detail["reconciliation"]["cash_payment_ratio"], "100.00%")
        self.assertEqual(
            [row["transaction_id"] for row in detail["payment_evidence"]],
            ["bank-1050", "bank-refund-35"],
        )

    def test_payment_application_allocates_bank_amount_by_oa_weight(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa("oa-4360", amount="4360.00", project_name="大理项目"),
                        self._oa("oa-5450", amount="5450.00", project_name="玉溪项目"),
                    ],
                    bank_rows=[self._bank("bank-10000", "10000.00")],
                )
            ]
        )

        self.assertEqual(
            {(row["allocation_id"], row["amount"]) for row in policy.serialized_cost_rows},
            {
                ("bank:bank-10000:oa:oa-4360", "4444.44"),
                ("bank:bank-10000:oa:oa-5450", "5555.56"),
            },
        )

    def test_two_bank_events_keep_real_accounts_after_relation_net_cost_allocation(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa("oa-1", amount="100.00", project_name="项目A"),
                        self._oa("oa-2", amount="200.00", project_name="项目B"),
                        self._oa("oa-3", amount="300.00", project_name="项目C"),
                    ],
                    bank_rows=[
                        self._bank("bank-1", "250.00", account_no="1111", account_label="建行 1111"),
                        self._bank("bank-2", "350.00", account_no="2222", account_label="民生 2222"),
                        self._bank(
                            "bank-refund",
                            "60.00",
                            direction="inflow",
                            tag_code="refund-code",
                            tag_label="付错退款",
                        ),
                    ],
                )
            ]
        )

        self.assertEqual(len(policy.serialized_cost_rows), 6)
        self.assertEqual(
            {row["payment_account_label"] for row in policy.serialized_cost_rows},
            {"建行 1111", "民生 2222"},
        )
        detail = policy.allocation(
            allocation_id="bank:bank-1:oa:oa-2",
            scope_kind="all",
            scope_value=None,
        )
        assert detail is not None
        self.assertEqual(detail["amount"], "75.00")
        self.assertEqual(detail["bank_event_amount"], "250.00")
        self.assertEqual(len(detail["payment_evidence"]), 3)
        self.assertEqual(
            sum((Decimal(row["amount"]) for row in policy.serialized_cost_rows), start=Decimal("0")),
            Decimal("540.00"),
        )

    def test_mismatched_oa_total_scales_item_cost_by_net_cost_over_oa_total(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa(
                            "oa-exp-1",
                            apply_type="日常报销",
                            amount="1200.00",
                            expense_items=[
                                self._item("lodging", "大理项目", "住宿费", "710.00"),
                                self._item("other", "大理项目", "其他", "490.00"),
                            ],
                        )
                    ],
                    bank_rows=[
                        self._bank("bank-out", "1050.00"),
                        self._bank(
                            "bank-refund",
                            "35.00",
                            direction="inflow",
                            tag_code="refund-code",
                            tag_label="付错退款",
                        ),
                    ],
                )
            ]
        )

        self.assertEqual(
            {(row["expense_type"], row["amount"]) for row in policy.serialized_cost_rows},
            {("住宿费", "600.54"), ("其他", "414.46")},
        )

    def test_any_ongoing_oa_excludes_entire_relation(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa("oa-ok", amount="100.00"),
                        self._oa("oa-progress", amount="300.00", workflow_status="processing", completed_at=""),
                    ],
                    bank_rows=[self._bank("bank-1", "400.00")],
                )
            ]
        )

        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual([row["transaction_id"] for row in policy.bank_flow_rows], ["bank-1"])
        self.assertEqual(
            policy.allocation_quality["excluded_by_reason"],
            [{"reason": "incomplete_oa_relation", "count": 1}],
        )

    def test_invalid_daily_item_excludes_entire_relation_without_parent_fallback(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa(
                            "oa-exp-1",
                            apply_type="日常报销",
                            amount="100.00",
                            project_name="表头项目不得兜底",
                            expense_items=[
                                self._item("valid", "项目A", "交通费", "40.00"),
                                self._item("missing-project", "", "交通费", "60.00"),
                            ],
                        )
                    ],
                    bank_rows=[self._bank("bank-1", "100.00")],
                )
            ]
        )

        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual(policy.allocation_quality["excluded_by_reason"], [{"reason": "missing_project", "count": 1}])

    def test_zero_oa_total_is_internal_guard_only(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", amount="0")], bank_rows=[self._bank("bank-1", "100.00")])]
        )
        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual([row["transaction_id"] for row in policy.bank_flow_rows], ["bank-1"])

    def test_daily_reimbursement_without_items_is_excluded(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-exp", apply_type="日常报销", expense_items=[])], bank_rows=[self._bank("bank-1", "100.00")])]
        )
        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual(
            policy.allocation_quality["excluded_by_reason"],
            [{"reason": "daily_reimbursement_without_items", "count": 1}],
        )

    def test_duplicate_expense_item_id_fails_entire_response(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa(
                            "oa-exp",
                            apply_type="日常报销",
                            expense_items=[
                                self._item("duplicate", "项目A", "交通费", "40.00"),
                                self._item("duplicate", "项目B", "住宿费", "60.00"),
                            ],
                        )
                    ],
                    bank_rows=[self._bank("bank-1", "100.00")],
                )
            ]
        )
        with self.assertRaises(CostStatisticsAllocationConflictError):
            _ = policy.serialized_cost_rows

    def test_same_oa_in_multiple_active_relations_fails_entire_response(self) -> None:
        oa = self._oa("oa-duplicate", amount="100.00")
        policy = self._policy(
            [
                self._group(group_id="case-1", oa_rows=[oa], bank_rows=[self._bank("bank-1", "100.00")]),
                self._group(group_id="case-2", oa_rows=[oa], bank_rows=[self._bank("bank-2", "100.00")]),
            ]
        )
        with self.assertRaises(CostStatisticsAllocationConflictError):
            _ = policy.serialized_cost_rows

    def test_only_paid_wrong_refund_in_same_relation_reduces_cost(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[self._oa("oa-1", amount="1015.00")],
                    bank_rows=[
                        self._bank("bank-out", "1050.00"),
                        self._bank("bank-refund", "35.00", direction="inflow", tag_code="refund-code", tag_label="付错退款"),
                        self._bank("bank-income", "20.00", direction="inflow", tag_code="interest", tag_label="利息"),
                    ],
                )
            ],
            settings={},
        )

        self.assertEqual(
            {(row["transaction_id"], row["amount"], row["direction"]) for row in policy.serialized_cost_rows},
            {("bank-out", "1015.00", "支出")},
        )
        self.assertEqual(policy.explorer_page(
            scope_kind="all", scope_value=None, view="project",
            filters={"project_name": "项目A", "expense_type": "设备采购"},
            cursor_values=None, page_size=50,
        )["summary"]["total_amount"], "1015.00")
        detail = policy.allocation(allocation_id="bank:bank-out:oa:oa-1", scope_kind="all", scope_value=None)
        assert detail is not None
        self.assertEqual(detail["reconciliation"]["paid_wrong_refund_total"], "35.00")
        self.assertEqual(detail["reconciliation"]["net_cash_cost"], "1015.00")
        self.assertEqual(detail["reconciliation"]["cash_payment_ratio"], "100.00%")
        self.assertEqual(
            [row["transaction_id"] for row in detail["payment_evidence"]],
            ["bank-out", "bank-refund"],
        )
        self.assertEqual(
            {(row["transaction_id"], row["direction"], row["amount"]) for row in policy.bank_flow_rows},
            {
                ("bank-out", "支出", "1050.00"),
                ("bank-refund", "收入", "35.00"),
                ("bank-income", "收入", "20.00"),
            },
        )

    def test_cross_month_paid_wrong_refund_reduces_original_outflow_month(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[self._oa("oa-1", amount="1015.00")],
                    bank_rows=[
                        self._bank("bank-out", "1050.00", trade_time="2026-08-31 10:00:00"),
                        self._bank(
                            "bank-refund",
                            "35.00",
                            direction="inflow",
                            tag_code="refund-code",
                            tag_label="付错退款",
                            trade_time="2026-09-01 10:00:00",
                        ),
                    ],
                )
            ]
        )

        august = policy.explorer_page(
            scope_kind="month",
            scope_value="2026-08",
            view="project",
            filters={},
            cursor_values=None,
            page_size=50,
        )
        september = policy.explorer_page(
            scope_kind="month",
            scope_value="2026-09",
            view="project",
            filters={},
            cursor_values=None,
            page_size=50,
        )
        all_time = policy.explorer_page(
            scope_kind="all",
            scope_value=None,
            view="project",
            filters={},
            cursor_values=None,
            page_size=50,
        )

        self.assertEqual(august["summary"]["total_amount"], "1015.00")
        self.assertEqual(september["summary"]["total_amount"], "0.00")
        self.assertEqual(september["primary_facets"], [])
        self.assertEqual(all_time["summary"]["total_amount"], "1015.00")

    def test_two_view_populations_use_bank_trade_date_and_reconcile_within_each_population(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", completed_at="2026-05-25 09:00:00")], bank_rows=[self._bank("bank-1", "100.00", trade_time="2026-06-01 09:00:00")])]
        )
        view_filters = {
            "project": {"project_name": "项目A", "expense_type": "设备采购"},
            "bank": {"payment_account_label": "建设银行 8106", "project_name": "项目A"},
            "expense_type": {"expense_type": "设备采购"},
            "bank_tag": {"bank_tag_primary_label": "未标记", "bank_tag_sub_label": "未标记"},
            "time": {},
        }
        totals: dict[str, str] = {}
        for view, filters in view_filters.items():
            may = policy.explorer_page(scope_kind="month", scope_value="2026-05", view=view, filters=filters, cursor_values=None, page_size=50)
            june = policy.explorer_page(scope_kind="month", scope_value="2026-06", view=view, filters=filters, cursor_values=None, page_size=50)
            self.assertEqual(may["summary"]["total_amount"], "0.00")
            totals[view] = june["summary"]["total_amount"]
        self.assertEqual(
            {totals[view] for view in {"project", "bank", "expense_type"}},
            {"100.00"},
        )
        self.assertEqual(
            {totals[view] for view in {"bank_tag", "time"}},
            {"100.00"},
        )

    def test_selected_no_oa_tag_adds_only_unpaired_outflows_to_virtual_project(self) -> None:
        paired = self._bank("paired", "100.00", tag_code="paired-only", tag_label="已配对专用标签")
        unpaired = self._bank("unpaired", "8.00", tag_code="fee", tag_label="手续费")
        unselected = self._bank("unselected", "5.00", tag_code="salary", tag_label="工资")
        income = self._bank("income", "1.00", direction="inflow", tag_code="fee", tag_label="手续费")
        settings = self._settings(
            tags=[("fee", "手续费"), ("salary", "工资")],
            projects=[("project-1", "云南溯源无 OA 分类", ["fee"])],
        )
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", amount="100.00")], bank_rows=[paired])],
            bank_rows=[paired, unpaired, unselected, income],
            settings=settings,
        )

        no_oa_rows = [row for row in policy.serialized_cost_rows if row["row_kind"] == "bank_transaction"]
        self.assertEqual(len(no_oa_rows), 1)
        self.assertEqual(no_oa_rows[0]["transaction_id"], "unpaired")
        self.assertEqual(no_oa_rows[0]["project_name"], "云南溯源无 OA 分类")
        self.assertEqual(no_oa_rows[0]["expense_type"], "无 OA 分类")
        self.assertEqual(
            {row["transaction_id"] for row in policy.bank_flow_rows},
            {"paired", "unpaired", "unselected", "income"},
        )

    def test_no_oa_defaults_empty_and_candidates_are_current_unpaired_outflow_tags(self) -> None:
        paired = self._bank("paired", "100.00", tag_code="paired-only", tag_label="已配对专用标签")
        unpaired = self._bank("unpaired", "8.00", tag_code="fee", tag_label="手续费")
        income = self._bank("income", "1.00", direction="inflow", tag_code="refund", tag_label="付错退款")
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1")], bank_rows=[paired, income])],
            bank_rows=[paired, unpaired, income],
            settings=self._settings(
                tags=[
                    ("paired-only", "已配对专用标签"),
                    ("fee", "手续费"),
                    ("refund", "付错退款"),
                ]
            ),
        )
        self.assertEqual(
            {(row["transaction_id"], row["amount"]) for row in policy.serialized_cost_rows},
            {("paired", "99.00")},
        )
        self.assertEqual([row["code"] for row in policy.no_oa_tag_candidates()], ["fee"])

    def test_any_active_oa_relation_protects_bank_row_from_no_oa_even_without_allocation_group(self) -> None:
        bank_row = self._bank("protected", "8.00", tag_code="fee", tag_label="手续费")
        policy = self._policy(
            [],
            bank_rows=[bank_row],
            oa_related_bank_ids=["protected"],
            settings=self._settings(
                tags=[("fee", "手续费")],
                projects=[("project-1", "云南溯源无 OA 分类", ["fee"])],
            ),
        )

        self.assertEqual(policy.no_oa_tag_candidates(), [])
        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual([row["transaction_id"] for row in policy.bank_flow_rows], ["protected"])

    def test_missing_oa_expense_type_uses_truthful_bucket(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", expense_type="")], bank_rows=[self._bank("bank-1", "100.00")])]
        )
        self.assertEqual(policy.serialized_cost_rows[0]["expense_type"], "未填写 OA 费用类型")
        self.assertEqual(policy.allocation_quality["excluded_allocation_count"], 0)

    def test_project_completion_setting_does_not_filter_historical_cost(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-a", project_name="已完成项目"), self._oa("oa-b", project_name="进行中项目")], bank_rows=[self._bank("bank-1", "200.00")])],
            settings={"projects": {"completed": [{"id": "P-1", "project_name": "已完成项目"}]}},
        )
        self.assertEqual(
            {(row["project_name"], row["amount"]) for row in policy.serialized_cost_rows},
            {("已完成项目", "100.00"), ("进行中项目", "100.00")},
        )
        self.assertEqual(policy.bank_flow_rows[0]["amount"], "200.00")

    def test_time_tag_default_all_includes_outflow_income_and_ongoing_oa_rows(self) -> None:
        outflow = self._bank("outflow", "10.00", tag_code="fee", tag_label="手续费")
        income = self._bank(
            "income",
            "3.00",
            direction="inflow",
            tag_code="interest",
            tag_label="利息",
        )
        ongoing = self._bank("ongoing", "20.00", tag_code="salary", tag_label="工资")
        policy = self._policy(
            [
                self._group(
                    oa_rows=[self._oa("oa-progress", workflow_status="processing", completed_at="")],
                    bank_rows=[ongoing],
                )
            ],
            bank_rows=[outflow, income, ongoing],
            settings=self._settings(tags=[("fee", "手续费"), ("interest", "利息"), ("salary", "工资")]),
        )

        self.assertEqual(
            {row["transaction_id"] for row in policy.bank_flow_rows},
            {"outflow", "income", "ongoing"},
        )
        summary = policy.explorer_page(
            scope_kind="all",
            scope_value=None,
            view="time",
            filters={},
            cursor_values=None,
            page_size=50,
        )["summary"]
        self.assertEqual(summary["expense_amount"], "30.00")
        self.assertEqual(summary["income_amount"], "3.00")
        self.assertEqual(summary["total_amount"], "27.00")

    def test_time_tag_custom_selection_filters_by_stable_tag_code(self) -> None:
        policy = self._policy(
            [],
            bank_rows=[
                self._bank("fee", "8.00", tag_code="fee", tag_label="手续费"),
                self._bank("salary", "9.00", tag_code="salary", tag_label="工资"),
                self._bank("untagged", "1.00"),
            ],
            settings=self._settings(
                tags=[("fee", "手续费"), ("salary", "工资")],
                time_mode="custom",
                time_selected=["fee", "__uncategorized__"],
            ),
        )

        self.assertEqual(
            {row["transaction_id"] for row in policy.bank_flow_rows},
            {"fee", "untagged"},
        )

    def test_missing_declared_oa_member_fails_closed_and_keeps_bank_protected(self) -> None:
        bank = self._bank("protected", "100.00", tag_code="fee", tag_label="手续费")
        group = self._group(
            oa_rows=[self._oa("oa-present")],
            bank_rows=[bank],
            declared_oa_ids=["oa-present", "oa-missing"],
        )
        policy = self._policy(
            [group],
            bank_rows=[bank],
            settings=self._settings(
                tags=[("fee", "手续费")],
                projects=[("project-1", "无 OA 项目", ["fee"])],
            ),
        )

        self.assertEqual(policy.serialized_cost_rows, [])
        self.assertEqual(policy.no_oa_tag_candidates(), [])
        self.assertEqual(
            policy.allocation_quality["excluded_by_reason"],
            [{"reason": "incomplete_oa_members", "count": 1}],
        )

    @staticmethod
    def _policy(
        groups: list[dict[str, object]],
        *,
        bank_rows: list[dict[str, object]] | None = None,
        oa_related_bank_ids: list[str] | None = None,
        settings: dict[str, object] | None = None,
    ) -> CostStatisticsPolicy:
        snapshot_bank_rows = list(bank_rows or [])
        if bank_rows is None:
            snapshot_bank_rows = [
                row
                for group in groups
                for row in list(group.get("bank_rows") or [])
                if isinstance(row, dict)
            ]
        return CostStatisticsPolicy(
            {
                "settings": settings or {},
                "bank_rows": snapshot_bank_rows,
                "cost_groups": groups,
                "oa_related_bank_ids": list(oa_related_bank_ids or []),
                "active_relation_count": len(groups),
                "available_years": ["2026"],
            },
        )

    @staticmethod
    def _settings(
        *,
        tags: list[tuple[str, str]],
        projects: list[tuple[str, str, list[str]]] | None = None,
        time_mode: str = "all",
        time_selected: list[str] | None = None,
    ) -> dict[str, object]:
        definitions = [
            {
                "code": code,
                "label": label,
                "path": [label],
                "source": "custom",
                "status": "active",
                "output_primary_label": label,
                "output_sub_label": label,
                "direction": "any",
                "account_scope": {"type": "any", "values": []},
                "rules": {
                    "match_fields": ["all_text"],
                    "contains_any": [label],
                    "contains_all": [],
                    "exact_any": [],
                    "regex_any": [],
                    "none_of": [],
                },
                "rule_code": code,
            }
            for code, label in tags
        ]
        return {
            "bank_transaction_tags": {"version": 1, "definitions": definitions},
            "cost_statistics_time_tag_selection": {
                "version": 1,
                "schema_version": 1,
                "mode": time_mode,
                "selected_tag_codes": list(time_selected or []),
            },
            "cost_statistics_no_oa_projects": {
                "version": 1,
                "schema_version": 1,
                "projects": [
                    {"id": project_id, "display_name": name, "tag_codes": codes}
                    for project_id, name, codes in list(projects or [])
                ],
            },
        }

    @staticmethod
    def _group(
        *,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        group_id: str = "case-1",
        declared_oa_ids: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "group_id": group_id,
            "declared_oa_ids": list(
                declared_oa_ids
                if declared_oa_ids is not None
                else [str(row.get("id") or "") for row in oa_rows]
            ),
            "oa_rows": oa_rows,
            "bank_rows": bank_rows,
        }

    @staticmethod
    def _oa(
        oa_id: str,
        *,
        apply_type: str = "支付申请",
        workflow_status: str = "completed",
        completed_at: str = "2026-05-25 09:00:00",
        amount: str = "100.00",
        project_name: str = "项目A",
        expense_type: str = "设备采购",
        expense_items: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "id": oa_id,
            "apply_type": apply_type,
            "workflow_status": workflow_status,
            "completed_at": completed_at,
            "amount": amount,
            "project_name": project_name,
            "expense_type": expense_type,
            "expense_content": "采购",
            "applicant": "杨丽萍",
            "counterparty_name": "供应商",
            "expense_items": expense_items or [],
        }

    @staticmethod
    def _item(item_id: str, project_name: str, expense_type: str, amount: str) -> dict[str, object]:
        return {
            "expense_item_id": item_id,
            "project_name": project_name,
            "expense_type": expense_type,
            "expense_content": expense_type,
            "amount": amount,
        }

    @staticmethod
    def _bank(
        bank_id: str,
        amount: str,
        *,
        trade_time: str = "2026-05-18 10:00:00",
        direction: str = "outflow",
        account_no: str = "8106",
        account_label: str = "建设银行 8106",
        tag_code: str = "",
        tag_label: str = "",
    ) -> dict[str, object]:
        return {
            "id": bank_id,
            "amount": amount,
            "txn_direction": direction,
            "direction": "收入" if direction == "inflow" else "支出",
            "trade_time": trade_time,
            "account_no": account_no,
            "payment_account_label": account_label,
            "counterparty_name": "供应商",
            "remark": "货款",
            "bank_tag_code": tag_code,
            "bank_tag_label": tag_label,
            "bank_tag_primary_label": tag_label,
            "bank_tag_sub_label": tag_label,
            "bank_tag_label_path": [tag_label] if tag_label else [],
        }


if __name__ == "__main__":
    unittest.main()
