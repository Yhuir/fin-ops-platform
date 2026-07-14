from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_api_payload_assembler import WorkbenchApiPayloadAssembler


class WorkbenchApiPayloadAssemblerTests(unittest.TestCase):
    def test_build_applies_legacy_grouped_payload_pipeline_in_order(self) -> None:
        calls: list[tuple[str, object]] = []

        def read_model_provider(month: str, **kwargs: object) -> dict[str, object]:
            calls.append(("read_model", {"month": month, **kwargs}))
            return {"payload": {"unpaired": {"groups": [{"group_id": "g1", "invoice_rows": []}]}}}

        def apply_oa_retention(payload: dict[str, object]) -> dict[str, object]:
            calls.append(("retention", payload))
            return {**payload, "retained": True}

        def append_etc_invoice_summary_rows(payload: dict[str, object]) -> None:
            calls.append(("etc", dict(payload)))
            payload["etc_appended"] = True

        def build_invoice_inventory(payload: dict[str, object]) -> dict[str, int]:
            calls.append(("inventory", dict(payload)))
            return {"system_total": 2}

        def derive_tags(payload: dict[str, object]) -> dict[str, object]:
            calls.append(("tags", dict(payload)))
            return {**payload, "tags_derived": True}

        assembler = WorkbenchApiPayloadAssembler(
            read_model_provider=read_model_provider,
            apply_oa_retention=apply_oa_retention,
            append_etc_invoice_summary_rows=append_etc_invoice_summary_rows,
            build_invoice_inventory=build_invoice_inventory,
            derive_tags=derive_tags,
        )

        payload = assembler.build("2026-05", visibility_key="user-a")

        self.assertEqual(payload["invoice_inventory"], {"system_total": 2})
        self.assertTrue(payload["tags_derived"])
        self.assertEqual(
            [name for name, _payload in calls],
            ["read_model", "retention", "etc", "inventory", "tags"],
        )
        self.assertEqual(
            calls[0][1],
            {
                "month": "2026-05",
                "visibility_key": "user-a",
            },
        )

    def test_non_dict_read_model_payload_uses_empty_payload(self) -> None:
        assembler = WorkbenchApiPayloadAssembler(
            read_model_provider=lambda *_args, **_kwargs: {"payload": None},
            apply_oa_retention=lambda payload: {**payload, "retained": True},
            append_etc_invoice_summary_rows=lambda _payload: None,
            build_invoice_inventory=lambda _payload: {"system_total": 0},
            derive_tags=lambda payload: payload,
        )

        payload = assembler.build("all")

        self.assertEqual(payload["invoice_inventory"], {"system_total": 0})
        self.assertTrue(payload["retained"])


if __name__ == "__main__":
    unittest.main()
