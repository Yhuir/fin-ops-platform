from __future__ import annotations

import unittest

from fin_ops_platform.services.cost_statistics_policy import (
    CostStatisticsAllocationConflictError,
    CostStatisticsPolicy,
)


class CostStatisticsPolicyTests(unittest.TestCase):
    def test_daily_reimbursement_uses_child_amounts_and_oa_completion_month(self) -> None:
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
                    bank_rows=[self._bank("bank-1050", "1050.00", trade_time="2026-08-01 15:58:31")],
                )
            ]
        )

        rows = policy.serialized_cost_rows
        self.assertEqual({row["amount"] for row in rows}, {"240.00", "710.00", "65.00"})
        dali = next(row for row in rows if row["project_name"] == "大理卷烟厂余热综合利用项目")
        self.assertEqual(dali["amount"], "710.00")
        self.assertEqual(dali["month"], "2026-07")
        self.assertEqual(dali["oa_completed_at"], "2026-07-23 18:00:00")
        self.assertEqual(dali["linked_bank_transaction_count"], 1)
        self.assertNotIn("transaction_id", dali)
        detail = policy.allocation(
            allocation_id="oa:oa-exp-1:item:item-2",
            scope_kind="month",
            scope_value="2026-07",
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["amount"], "710.00")
        self.assertEqual(detail["payment_evidence"][0]["amount"], "1050.00")
        self.assertEqual(detail["reconciliation"]["oa_allocation_total"], "1015.00")
        self.assertEqual(detail["reconciliation"]["difference"], "-35.00")

    def test_payment_application_keeps_oa_amount_when_bank_amount_differs(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa("oa-4360", amount="4360.00", project_name="大理项目"),
                        self._oa("oa-5450", amount="5450.00", project_name="大理项目"),
                    ],
                    bank_rows=[self._bank("bank-9810", "9810.00")],
                )
            ]
        )

        self.assertEqual(
            {(row["allocation_id"], row["amount"]) for row in policy.serialized_cost_rows},
            {("oa:oa-4360", "4360.00"), ("oa:oa-5450", "5450.00")},
        )
        detail = policy.allocation(
            allocation_id="oa:oa-4360",
            scope_kind="all",
            scope_value=None,
        )
        assert detail is not None
        self.assertEqual(detail["amount"], "4360.00")
        self.assertEqual(detail["payment_evidence"][0]["amount"], "9810.00")
        self.assertEqual(detail["reconciliation"]["status"], "balanced")

    def test_three_oa_two_bank_uses_each_oa_amount_without_proportional_allocation(self) -> None:
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
                    ],
                )
            ]
        )

        self.assertEqual([row["amount"] for row in reversed(policy.serialized_cost_rows)], ["100.00", "200.00", "300.00"])
        self.assertTrue(all(row["payment_account_label"] == "混合支付账户" for row in policy.serialized_cost_rows))
        detail = policy.allocation(allocation_id="oa:oa-2", scope_kind="all", scope_value=None)
        assert detail is not None
        self.assertEqual(detail["amount"], "200.00")
        self.assertEqual(len(detail["payment_evidence"]), 2)
        self.assertEqual(detail["reconciliation"]["oa_allocation_total"], "600.00")
        self.assertEqual(detail["reconciliation"]["bank_outflow_total"], "600.00")

    def test_same_payment_account_is_assigned_to_every_oa_unit(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[self._oa("oa-1", amount="300.00")],
                    bank_rows=[
                        self._bank("bank-1", "100.00"),
                        self._bank("bank-2", "200.00"),
                    ],
                )
            ]
        )
        self.assertEqual(policy.serialized_cost_rows[0]["payment_account_label"], "建设银行 8106")

    def test_only_explicit_completed_oa_with_completion_time_is_eligible(self) -> None:
        policy = self._policy(
            [
                self._group(
                    oa_rows=[
                        self._oa("oa-ok", amount="100.00"),
                        self._oa("oa-empty", amount="200.00", workflow_status=""),
                        self._oa("oa-progress", amount="300.00", workflow_status="processing"),
                        self._oa("oa-no-time", amount="400.00", completed_at=""),
                    ],
                    bank_rows=[self._bank("bank-1", "1000.00")],
                )
            ]
        )

        self.assertEqual([row["oa_id"] for row in policy.serialized_cost_rows], ["oa-ok"])
        self.assertEqual(policy.allocation_quality["excluded_allocation_count"], 3)

    def test_invalid_daily_items_are_excluded_without_parent_fallback(self) -> None:
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

        self.assertEqual([(row["project_name"], row["amount"]) for row in policy.serialized_cost_rows], [("项目A", "40.00")])
        self.assertEqual(policy.allocation_quality["excluded_by_reason"], [{"reason": "missing_project", "count": 1}])

    def test_daily_reimbursement_without_items_is_visible_exclusion(self) -> None:
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

    def test_income_does_not_reduce_oa_cost_or_appear_as_payment_evidence(self) -> None:
        income = self._bank("bank-income", "35.00", direction="inflow")
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", amount="100.00")], bank_rows=[self._bank("bank-out", "100.00"), income])]
        )
        self.assertEqual(policy.serialized_cost_rows[0]["amount"], "100.00")
        detail = policy.allocation(allocation_id="oa:oa-1", scope_kind="all", scope_value=None)
        assert detail is not None
        self.assertEqual([row["transaction_id"] for row in detail["payment_evidence"]], ["bank-out"])

    def test_oa_scope_uses_completion_time_while_bank_scope_uses_trade_time(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-1", completed_at="2026-05-25 09:00:00")], bank_rows=[self._bank("bank-1", "100.00", trade_time="2026-06-01 09:00:00")])]
        )
        self.assertEqual(
            policy.explorer_page(
                scope_kind="month", scope_value="2026-05", view="project",
                filters={"project_name": "项目A", "expense_type": "设备采购"},
                cursor_values=None, page_size=50,
            )["row_count"],
            1,
        )
        self.assertEqual(
            policy.explorer_page(
                scope_kind="month", scope_value="2026-05", view="time", filters={},
                cursor_values=None, page_size=50,
            )["row_count"],
            0,
        )
        self.assertEqual(
            policy.explorer_page(
                scope_kind="month", scope_value="2026-06", view="time", filters={},
                cursor_values=None, page_size=50,
            )["row_count"],
            1,
        )

    def test_active_project_scope_filters_each_allocation_unit(self) -> None:
        policy = self._policy(
            [self._group(oa_rows=[self._oa("oa-a", project_name="已完成项目"), self._oa("oa-b", project_name="进行中项目")], bank_rows=[self._bank("bank-1", "200.00")])],
            settings={"projects": {"completed": [{"id": "P-1", "project_name": "已完成项目"}]}},
            project_scope="active",
        )
        self.assertEqual([row["project_name"] for row in policy.serialized_cost_rows], ["进行中项目"])

    def test_bank_view_remains_bank_transaction_shaped(self) -> None:
        policy = self._policy([], bank_rows=[self._bank("bank-1", "100.00")])
        row = policy.bank_flow_rows[0]
        self.assertEqual(row["row_kind"], "bank_transaction")
        self.assertEqual(row["entry_id"], "bank-1")
        self.assertEqual(row["trade_time"], "2026-05-18 10:00:00")

    @staticmethod
    def _policy(
        groups: list[dict[str, object]],
        *,
        bank_rows: list[dict[str, object]] | None = None,
        settings: dict[str, object] | None = None,
        project_scope: str = "all",
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
                "active_relation_count": len(groups),
                "available_years": ["2026"],
            },
            project_scope=project_scope,
        )

    @staticmethod
    def _group(
        *,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        group_id: str = "case-1",
    ) -> dict[str, object]:
        return {"group_id": group_id, "oa_rows": oa_rows, "bank_rows": bank_rows}

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
        }


if __name__ == "__main__":
    unittest.main()
