from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_raw_payload_assembler import WorkbenchRawPayloadAssembler


class WorkbenchRawPayloadAssemblerTests(unittest.TestCase):
    def test_live_branch_syncs_and_applies_pair_relations_then_overrides(self) -> None:
        calls: list[tuple[str, object]] = []

        def sync_live() -> None:
            calls.append(("sync_live", None))

        def build_live(month: str) -> dict[str, object]:
            calls.append(("build_live", month))
            return {"source": "live"}

        def sync_oa_invoice_offset(payload: dict[str, object]) -> None:
            calls.append(("sync_oa_offset", dict(payload)))
            payload["oa_offset_synced"] = True

        def repair(payload: dict[str, object]) -> None:
            calls.append(("repair", dict(payload)))
            payload["repaired"] = True

        def apply_pair(payload: dict[str, object], **kwargs: object) -> dict[str, object]:
            calls.append(("pair", {"payload": dict(payload), **kwargs}))
            return {**payload, "paired": True}

        def apply_overrides(payload: dict[str, object]) -> dict[str, object]:
            calls.append(("override", dict(payload)))
            return {**payload, "overridden": True}

        assembler = WorkbenchRawPayloadAssembler(
            has_live_rows_for_month=lambda _month: True,
            sync_live_auto_pair_relations=sync_live,
            build_live_workbench_row_payload=build_live,
            build_oa_workbench_row_payload=lambda _month: {"source": "oa"},
            sync_oa_invoice_offset_auto_pair_relations=sync_oa_invoice_offset,
            repair_active_relations_with_oa_attachment_context=repair,
            apply_pair_relations_to_payload=apply_pair,
            apply_overrides_to_payload=apply_overrides,
        )

        payload = assembler.build("2026-05", supplement_missing_pair_relation_rows=False)

        self.assertEqual(payload["source"], "live")
        self.assertTrue(payload["overridden"])
        self.assertEqual(
            [name for name, _payload in calls],
            ["sync_live", "build_live", "sync_oa_offset", "repair", "pair", "override"],
        )
        self.assertEqual(calls[4][1]["supplement_missing_rows"], False)

    def test_oa_branch_skips_live_sync(self) -> None:
        calls: list[str] = []

        assembler = WorkbenchRawPayloadAssembler(
            has_live_rows_for_month=lambda _month: False,
            sync_live_auto_pair_relations=lambda: calls.append("sync_live"),
            build_live_workbench_row_payload=lambda _month: {"source": "live"},
            build_oa_workbench_row_payload=lambda month: calls.append(f"build_oa:{month}") or {"source": "oa"},
            sync_oa_invoice_offset_auto_pair_relations=lambda _payload: calls.append("sync_oa_offset"),
            repair_active_relations_with_oa_attachment_context=lambda _payload: calls.append("repair"),
            apply_pair_relations_to_payload=lambda payload, **_kwargs: calls.append("pair") or payload,
            apply_overrides_to_payload=lambda payload: calls.append("override") or payload,
        )

        payload = assembler.build("all")

        self.assertEqual(payload, {"source": "oa"})
        self.assertEqual(calls, ["build_oa:all", "sync_oa_offset", "repair", "pair", "override"])


if __name__ == "__main__":
    unittest.main()
