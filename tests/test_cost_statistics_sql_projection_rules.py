import unittest

from fin_ops_platform.services.cost_statistics_sql_projection import CostStatisticsSqlProjectionBuilder


class _ProjectionConnection:
    def __init__(self, settings_payload: dict[str, object] | None = None) -> None:
        self.settings_payload = settings_payload or {}

    def fetch_one(self, sql: str, _params: tuple = ()) -> dict[str, object] | None:
        if "from app.app_settings" in " ".join(sql.lower().split()):
            return {"settings_payload": self.settings_payload}
        return None


class CostStatisticsSqlProjectionRuleTests(unittest.TestCase):
    def _payload(
        self,
        groups: list[dict[str, object]],
        *,
        project_scope: str = "all",
        settings_payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        builder = CostStatisticsSqlProjectionBuilder(
            connection=_ProjectionConnection(settings_payload),
            read_model_repository=object(),
        )
        return builder._build_explorer_payload(
            "2026-03",
            project_scope=project_scope,
            workbench_groups=groups,
            bank_detail_payload={"rows": [], "month_rows": []},
        )

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

    def test_projection_rejects_excluded_oa_rows(self) -> None:
        excluded_fields = (
            {"cost_excluded": True},
            {"tags": ["冲"]},
            {"oa_bank_relation": {"code": "oa_invoice_offset_auto_match"}},
        )
        for index, excluded in enumerate(excluded_fields):
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
                self.assertEqual(payload["summary"]["transaction_count"], 0)
                self.assertEqual(payload["time_rows"], [])

    def test_projection_rejects_loan_incomplete_and_conflicting_oa_contexts(self) -> None:
        cases = (
            [self._oa_row(expense_type="借款")],
            [self._oa_row(expense_content="")],
            [self._oa_row(), self._oa_row(project_name="另一个项目")],
        )
        for index, oa_rows in enumerate(cases):
            with self.subTest(index=index):
                payload = self._payload([self._group(group_id=f"invalid-{index}", oa_rows=oa_rows)])
                self.assertEqual(payload["summary"]["transaction_count"], 0)

    def test_projection_keeps_hint_only_and_excludes_exclude_all(self) -> None:
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

        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "1,000.00")
        self.assertEqual(payload["time_rows"][0]["group_id"], "cash-hint")

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

    def test_projection_reads_special_policy_from_group_member(self) -> None:
        group = self._group(group_id="member-policy")
        group["oa_rows"][0]["special_metadata"] = {"cost_policy": "exclude_all"}

        payload = self._payload([group])

        self.assertEqual(payload["summary"]["transaction_count"], 0)

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
        builder = CostStatisticsSqlProjectionBuilder(
            connection=_ProjectionConnection(),
            read_model_repository=object(),
        )

        with self.assertRaisesRegex(ValueError, "project_scope must be active or all"):
            builder.rebuild_cost_statistics_read_model_scope(
                "finished:2026-03",
                tenant_id="default",
                source_version=1,
            )

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
