from __future__ import annotations

from datetime import UTC, datetime
import unittest

from fin_ops_platform.services.workbench_oa_attachment_repair_context_executor import (
    WorkbenchOaAttachmentRepairContextExecutor,
)


class _CommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        return {
            "relation": {
                "case_id": kwargs["case_id"],
                "month_scope": kwargs["month_scope"],
            },
            "changed_case_ids": [kwargs["case_id"]],
        }


class WorkbenchOaAttachmentRepairContextExecutorTests(unittest.TestCase):
    def _executor(
        self,
        *,
        rows_by_id: dict[str, dict[str, object]],
        attachment_row_ids_by_oa_id: dict[str, list[str]],
        active_relations: list[dict[str, object]],
        dedicated_modes: set[str] | None = None,
    ) -> tuple[
        WorkbenchOaAttachmentRepairContextExecutor,
        _CommandService,
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        command_service = _CommandService()
        persist_calls: list[dict[str, object]] = []
        lifecycle_calls: list[dict[str, object]] = []
        dedicated_modes = dedicated_modes or set()
        executor = WorkbenchOaAttachmentRepairContextExecutor(
            raw_payload_rows_by_id=lambda payload: rows_by_id,
            attachment_row_ids_by_oa_id=lambda rows: attachment_row_ids_by_oa_id,
            active_relations=lambda: active_relations,
            relation_requires_dedicated_withdraw_action=lambda relation: str(
                relation.get("relation_mode") or ""
            ) in dedicated_modes,
            row_type_for_row_id=lambda row_id: "bank" if row_id.startswith("bk-") else "oa",
            serialize_value=lambda value: dict(value) if isinstance(value, dict) else value,
            rows_by_type=self._rows_by_type,
            amount_check_for_rows_by_type=lambda rows: {"status": "matched", "row_counts": {k: len(v) for k, v in rows.items()}},
            scope_keys_for_row_ids=lambda **kwargs: {
                "all",
                str(kwargs.get("month") or ""),
                str(kwargs.get("month_scope") or ""),
            }
            - {""},
            command_service_provider=lambda: command_service,
            persist_pair_relations=lambda **kwargs: persist_calls.append(dict(kwargs)),
            execute_lifecycle_event=lambda event_name, **kwargs: lifecycle_calls.append(
                {"event_name": event_name, **kwargs}
            ),
            clock=lambda: datetime(2026, 6, 25, tzinfo=UTC),
            history_note="repair note",
        )
        return executor, command_service, persist_calls, lifecycle_calls

    def test_repair_returns_false_without_payload_rows_or_attachment_context(self) -> None:
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            rows_by_id={},
            attachment_row_ids_by_oa_id={},
            active_relations=[],
        )

        self.assertFalse(executor.repair({"month": "2026-05"}))
        self.assertEqual(command_service.confirm_calls, [])
        self.assertEqual(persist_calls, [])
        self.assertEqual(lifecycle_calls, [])

        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            rows_by_id={"oa-1": {"id": "oa-1", "type": "oa"}},
            attachment_row_ids_by_oa_id={},
            active_relations=[],
        )

        self.assertFalse(executor.repair({"month": "2026-05"}))
        self.assertEqual(command_service.confirm_calls, [])

    def test_repair_adds_missing_attachment_rows_and_preserves_replace_existing_context(self) -> None:
        rows_by_id = {
            "oa-1": {"id": "oa-1", "type": "oa"},
            "bk-1": {"id": "bk-1", "type": "bank"},
            "inv-1": {"id": "inv-1", "type": "invoice"},
        }
        active_relation = {
            "case_id": "CASE-1",
            "row_ids": ["oa-1", "bk-1"],
            "row_types": ["oa", "bank"],
            "relation_mode": "manual_confirmed",
            "created_by": "tester",
            "month_scope": "2026-05",
            "display_tags": [" linked ", ""],
        }
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            rows_by_id=rows_by_id,
            attachment_row_ids_by_oa_id={"oa-1": ["inv-1"]},
            active_relations=[active_relation],
        )

        changed = executor.repair({"month": "2026-05"})

        self.assertTrue(changed)
        call = command_service.confirm_calls[0]
        self.assertEqual(call["case_id"], "CASE-1")
        self.assertEqual(call["row_ids"], ["oa-1", "bk-1", "inv-1"])
        self.assertEqual(call["row_types"], ["oa", "bank", "invoice"])
        self.assertEqual(call["actor_id"], "system_repair")
        self.assertEqual(call["relation_created_by"], "tester")
        self.assertEqual(call["history_operation_type"], "repair_missing_oa_attachment_context")
        self.assertEqual(call["history_note"], "repair note")
        self.assertEqual(call["display_tags"], ["linked"])
        self.assertTrue(call["replace_existing"])
        self.assertEqual(call["before_relations"], [active_relation])
        self.assertEqual(call["occurred_at"], "2026-06-25T00:00:00+00:00")
        self.assertEqual(call["amount_check"], {"status": "matched", "row_counts": {"oa": 1, "bank": 1, "invoice": 1}})
        self.assertEqual(persist_calls, [{"changed_case_ids": ["CASE-1"]}])
        self.assertEqual(lifecycle_calls[0]["event_name"], "pair_relation_changed")
        self.assertEqual(set(lifecycle_calls[0]["scope_keys"]), {"all", "2026-05"})
        self.assertEqual(lifecycle_calls[0]["metadata"], {"source": "repair_active_relations_with_oa_attachment_context"})

    def test_repair_skips_relations_without_bank_or_dedicated_withdraw_mode(self) -> None:
        rows_by_id = {
            "oa-1": {"id": "oa-1", "type": "oa"},
            "inv-1": {"id": "inv-1", "type": "invoice"},
        }
        active_relations = [
            {
                "case_id": "CASE-NO-BANK",
                "row_ids": ["oa-1"],
                "row_types": ["oa"],
                "relation_mode": "manual_confirmed",
            },
            {
                "case_id": "CASE-DEDICATED",
                "row_ids": ["oa-1", "bk-1"],
                "row_types": ["oa", "bank"],
                "relation_mode": "no_oa_bank_batch",
            },
        ]
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            rows_by_id=rows_by_id,
            attachment_row_ids_by_oa_id={"oa-1": ["inv-1"]},
            active_relations=active_relations,
            dedicated_modes={"no_oa_bank_batch"},
        )

        self.assertFalse(executor.repair({"month": "2026-05"}))
        self.assertEqual(command_service.confirm_calls, [])
        self.assertEqual(persist_calls, [])
        self.assertEqual(lifecycle_calls, [])

    @staticmethod
    def _rows_by_type(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        rows_by_type: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type") or "")
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type


if __name__ == "__main__":
    unittest.main()
