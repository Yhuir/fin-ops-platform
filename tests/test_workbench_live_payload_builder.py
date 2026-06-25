from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_live_payload_builder import WorkbenchLivePayloadBuilder


class WorkbenchLivePayloadBuilderTests(unittest.TestCase):
    def test_build_merges_live_and_oa_payload_then_serializes(self) -> None:
        calls: list[tuple[str, object]] = []

        def get_live(month: str) -> dict[str, object]:
            calls.append(("live", month))
            return {"live": month}

        def get_oa(month: str) -> dict[str, object]:
            calls.append(("oa", month))
            return {"oa": month}

        def merge(live_payload: dict[str, object], oa_payload: dict[str, object]) -> dict[str, object]:
            calls.append(("merge", {"live": live_payload, "oa": oa_payload}))
            return {"merged": [live_payload, oa_payload]}

        def serialize(value: object) -> object:
            calls.append(("serialize", value))
            return {"serialized": value}

        builder = WorkbenchLivePayloadBuilder(
            get_live_workbench=get_live,
            build_oa_workbench_row_payload=get_oa,
            merge_live_with_oa_rows=merge,
            serialize_value=serialize,
        )

        payload = builder.build("2026-05")

        self.assertEqual(payload, {"serialized": {"merged": [{"live": "2026-05"}, {"oa": "2026-05"}]}})
        self.assertEqual([name for name, _payload in calls], ["live", "oa", "merge", "serialize"])

    def test_non_dict_serialized_payload_returns_empty_payload(self) -> None:
        builder = WorkbenchLivePayloadBuilder(
            get_live_workbench=lambda _month: {"live": True},
            build_oa_workbench_row_payload=lambda _month: {"oa": True},
            merge_live_with_oa_rows=lambda _live, _oa: {"merged": True},
            serialize_value=lambda _value: None,
        )

        self.assertEqual(builder.build("all"), {})


if __name__ == "__main__":
    unittest.main()
