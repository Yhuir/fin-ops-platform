from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.services.workbench_retained_all_oa_payload_builder import WorkbenchRetainedAllOaPayloadBuilder


class WorkbenchRetainedAllOaPayloadBuilderTests(unittest.TestCase):
    def test_no_cutoff_uses_all_payload_and_promotes_payload_months_when_signal_exists(self) -> None:
        promoted: list[set[str]] = []
        builder = WorkbenchRetainedAllOaPayloadBuilder(
            retention_cutoff_date=lambda: None,
            get_all_workbench_payload=lambda: {"month": "all", "has_attachment": True},
            serialize_value=lambda value: dict(value),
            raw_payload_has_oa_attachment_invoice_signal=lambda payload: bool(payload.get("has_attachment")),
            oa_months_from_raw_workbench_payload=lambda _payload: {"2026-03", "2026-04"},
            promote_oa_attachment_invoices_to_canonical=lambda scopes: promoted.append(set(scopes)) or len(scopes),
            retained_oa_months_for_all_scope=lambda _cutoff: [],
            supplemental_retained_oa_row_ids=lambda _cutoff: [],
            suppress_attachment_invoice_background_parse=None,
            sync_oa_rows=lambda _month: None,
            sync_oa_row_ids=lambda _row_ids: None,
            record_snapshots=lambda: [],
            raw_oa_payload_for_selected_scope=lambda **_kwargs: {},
            is_month_scope=lambda _scope: True,
        )

        payload = builder.build()

        self.assertEqual(payload["month"], "all")
        self.assertEqual(promoted, [{"2026-03", "2026-04"}])

    def test_cutoff_syncs_retained_scopes_and_promotes_month_scopes(self) -> None:
        calls: list[tuple[str, object]] = []

        @contextmanager
        def suppress_parse():
            calls.append(("parse_enter", None))
            yield
            calls.append(("parse_exit", None))

        builder = WorkbenchRetainedAllOaPayloadBuilder(
            retention_cutoff_date=lambda: object(),
            get_all_workbench_payload=lambda: {},
            serialize_value=lambda value: dict(value),
            raw_payload_has_oa_attachment_invoice_signal=lambda _payload: True,
            oa_months_from_raw_workbench_payload=lambda _payload: set(),
            promote_oa_attachment_invoices_to_canonical=lambda scopes: calls.append(("promote", set(scopes))) or len(scopes),
            retained_oa_months_for_all_scope=lambda _cutoff: ["2026-03"],
            supplemental_retained_oa_row_ids=lambda _cutoff: ["oa-old"],
            suppress_attachment_invoice_background_parse=suppress_parse,
            sync_oa_rows=lambda month: calls.append(("sync_month", month)),
            sync_oa_row_ids=lambda row_ids: calls.append(("sync_ids", list(row_ids))),
            record_snapshots=lambda: [{"id": "oa-old", "_month": "2026-02"}, {"id": "other", "_month": "bad"}],
            raw_oa_payload_for_selected_scope=lambda **kwargs: calls.append(("raw_scope", kwargs)) or {"has_attachment": True},
            is_month_scope=lambda scope: scope.startswith("2026-"),
        )

        payload = builder.build()

        self.assertEqual(payload, {"has_attachment": True})
        self.assertEqual(
            calls,
            [
                ("parse_enter", None),
                ("sync_month", "2026-03"),
                ("sync_ids", ["oa-old"]),
                ("parse_exit", None),
                (
                    "raw_scope",
                    {"months": {"2026-03"}, "supplemental_oa_row_ids": {"oa-old"}},
                ),
                ("promote", {"2026-02", "2026-03"}),
            ],
        )

    def test_non_dict_serialized_payload_returns_empty_payload(self) -> None:
        builder = WorkbenchRetainedAllOaPayloadBuilder(
            retention_cutoff_date=lambda: None,
            get_all_workbench_payload=lambda: object(),
            serialize_value=lambda _value: None,
            raw_payload_has_oa_attachment_invoice_signal=lambda _payload: False,
            oa_months_from_raw_workbench_payload=lambda _payload: set(),
            promote_oa_attachment_invoices_to_canonical=lambda _scopes: 0,
            retained_oa_months_for_all_scope=lambda _cutoff: [],
            supplemental_retained_oa_row_ids=lambda _cutoff: [],
            suppress_attachment_invoice_background_parse=None,
            sync_oa_rows=lambda _month: None,
            sync_oa_row_ids=lambda _row_ids: None,
            record_snapshots=lambda: [],
            raw_oa_payload_for_selected_scope=lambda **_kwargs: {},
            is_month_scope=lambda _scope: True,
        )

        self.assertEqual(builder.build(), {})


if __name__ == "__main__":
    unittest.main()
