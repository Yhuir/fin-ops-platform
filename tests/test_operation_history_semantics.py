from __future__ import annotations

import unittest

from fin_ops_platform.services.operation_history_semantics import (
    operation_semantics,
    semantics_from_audit_row,
)


class OperationHistorySemanticsTests(unittest.TestCase):
    def test_known_mutations_have_stable_user_facing_semantics(self) -> None:
        cases = (
            ("POST", "/api/workbench/actions/confirm-link", "确认关联", "关联关系"),
            ("PUT", "/api/bank-details/auto-tag-rules", "保存自动标签规则", "流水标签规则"),
            ("POST", "/imports/invoices/manual/preview", "预览发票录入", "发票录入"),
            ("POST", "/api/oa-pending-payments/writeback-paid", "确认已支付", "OA 付款项"),
            ("POST", "/api/workbench/actions/confirm-link/preview", "预览确认关联", "关联关系"),
            ("POST", "/api/tax-offset/calculate", "计算抵扣方案", "税金抵扣计划"),
            (
                "POST",
                "/api/workbench/oa-invoice-supplements/manual",
                "录入并关联 OA 发票",
                "OA 发票关联",
            ),
            (
                "POST",
                "/api/workbench/oa-invoice-supplements/documents",
                "上传 OA 补充凭证",
                "OA 补充凭证",
            ),
            (
                "DELETE",
                "/api/workbench/oa-invoice-supplements/documents/document-1",
                "删除 OA 补充凭证",
                "OA 补充凭证",
            ),
            (
                "POST",
                "/api/pending-invoices/rows/row-1/attach-existing-invoice/preview",
                "预览发票关联",
                "发票关联",
            ),
        )

        for method, route, action_label, object_label in cases:
            with self.subTest(route=route):
                semantics = operation_semantics(method, route)
                self.assertEqual(semantics.action_label, action_label)
                self.assertEqual(semantics.object_label, object_label)
                self.assertNotIn("/api/", str(semantics))
                self.assertNotIn("HTTP", str(semantics))

    def test_stored_semantics_are_the_projection_source_of_truth(self) -> None:
        semantics = semantics_from_audit_row(
            {
                "action": "legacy.value",
                "object_type": "bank_transaction",
                "payload": {
                    "metadata": {
                        "action_code": "bank.transactions.update_category",
                        "action_label": "更新流水分类",
                        "object_label": "银行流水",
                        "description": "批量更新银行流水分类。",
                    }
                },
            }
        )

        self.assertEqual(semantics.action_code, "bank.transactions.update_category")
        self.assertEqual(semantics.action_label, "更新流水分类")
        self.assertEqual(semantics.object_label, "银行流水")

    def test_unknown_mutation_uses_bounded_page_fallback_without_raw_route(self) -> None:
        semantics = operation_semantics(
            "PATCH",
            "/api/bank-details/future-action/secret-id",
            page_key="bank-details",
        )

        self.assertEqual(semantics.action_label, "更新银行流水")
        self.assertEqual(semantics.object_label, "银行流水")
        self.assertNotIn("future-action", str(semantics))


if __name__ == "__main__":
    unittest.main()
