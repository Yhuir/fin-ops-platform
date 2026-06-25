from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_oa_payload_builder import WorkbenchOaPayloadBuilder


class WorkbenchOaPayloadBuilderTests(unittest.TestCase):
    def test_month_scope_serializes_promotes_and_appends_canonical_rows(self) -> None:
        calls: list[tuple[str, object]] = []

        def promote(scopes: set[str]) -> int:
            calls.append(("promote", set(scopes)))
            return len(scopes)

        def append(payload: dict[str, object]) -> None:
            calls.append(("append", dict(payload)))
            payload["canonical_appended"] = True

        builder = WorkbenchOaPayloadBuilder(
            use_retained_all_payload=lambda _month: False,
            build_retained_all_oa_row_payload=lambda: {"retained": True},
            get_workbench_payload=lambda month: calls.append(("get", month)) or {"month": month},
            serialize_value=lambda value: calls.append(("serialize", value)) or dict(value),
            is_month_scope=lambda month: month == "2026-05",
            promote_oa_attachment_invoices_to_canonical=promote,
            append_canonical_oa_attachment_invoice_rows=append,
        )

        payload = builder.build("2026-05")

        self.assertEqual(payload["month"], "2026-05")
        self.assertTrue(payload["canonical_appended"])
        self.assertEqual([name for name, _payload in calls], ["get", "serialize", "promote", "append"])
        self.assertEqual(calls[2][1], {"2026-05"})

    def test_retained_all_branch_skips_normal_get_and_promotion(self) -> None:
        calls: list[str] = []

        builder = WorkbenchOaPayloadBuilder(
            use_retained_all_payload=lambda month: month == "all",
            build_retained_all_oa_row_payload=lambda: calls.append("retained") or {"month": "all"},
            get_workbench_payload=lambda _month: calls.append("get") or {},
            serialize_value=lambda value: calls.append("serialize") or value,
            is_month_scope=lambda _month: True,
            promote_oa_attachment_invoices_to_canonical=lambda _scopes: calls.append("promote") or 0,
            append_canonical_oa_attachment_invoice_rows=lambda _payload: calls.append("append"),
        )

        payload = builder.build("all")

        self.assertEqual(payload, {"month": "all"})
        self.assertEqual(calls, ["retained", "append"])

    def test_non_dict_serialized_payload_uses_empty_payload_before_append(self) -> None:
        appended_payloads: list[dict[str, object]] = []
        builder = WorkbenchOaPayloadBuilder(
            use_retained_all_payload=lambda _month: False,
            build_retained_all_oa_row_payload=lambda: {"retained": True},
            get_workbench_payload=lambda _month: object(),
            serialize_value=lambda _value: None,
            is_month_scope=lambda _month: False,
            promote_oa_attachment_invoices_to_canonical=lambda _scopes: 0,
            append_canonical_oa_attachment_invoice_rows=lambda payload: appended_payloads.append(dict(payload)),
        )

        payload = builder.build("all")

        self.assertEqual(payload, {})
        self.assertEqual(appended_payloads, [{}])


if __name__ == "__main__":
    unittest.main()
