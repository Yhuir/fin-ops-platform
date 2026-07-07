from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_oa_invoice_offset_sync_executor import (
    WorkbenchOaInvoiceOffsetSyncExecutor,
)


class _CommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []
        self.cancel_calls: list[dict[str, object]] = []

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        return {"changed_case_ids": [kwargs["case_id"]]}

    def cancel_relation(self, **kwargs: object) -> dict[str, object]:
        self.cancel_calls.append(dict(kwargs))
        return {"changed_case_ids": [kwargs["case_id"]]}


class WorkbenchOaInvoiceOffsetSyncExecutorTests(unittest.TestCase):
    def _executor(
        self,
        *,
        desired_relations: dict[str, dict[str, object]],
        active_relations: list[dict[str, object]] | None = None,
        scanned_row_ids: set[str] | None = None,
    ) -> tuple[WorkbenchOaInvoiceOffsetSyncExecutor, _CommandService, list[dict[str, object]], list[dict[str, object]]]:
        command_service = _CommandService()
        persist_calls: list[dict[str, object]] = []
        lifecycle_calls: list[dict[str, object]] = []
        executor = WorkbenchOaInvoiceOffsetSyncExecutor(
            desired_relations_builder=lambda payload: desired_relations,
            raw_payload_row_ids=lambda payload: scanned_row_ids if scanned_row_ids is not None else {"oa-1", "inv-1"},
            active_relations_for_mode=lambda relation_mode: list(active_relations or []),
            command_service_provider=lambda: command_service,
            persist_pair_relations=lambda **kwargs: persist_calls.append(dict(kwargs)),
            execute_lifecycle_event=lambda event_name, **kwargs: lifecycle_calls.append(
                {"event_name": event_name, **kwargs}
            ),
            relation_mode="oa_invoice_offset_auto_match",
        )
        return executor, command_service, persist_calls, lifecycle_calls

    def test_sync_skips_when_active_relation_already_matches(self) -> None:
        desired = {
            "CASE-OA-OFFSET-oa-1": {
                "case_id": "CASE-OA-OFFSET-oa-1",
                "row_ids": ["oa-1", "inv-1"],
                "row_types": ["oa", "invoice"],
                "month_scope": "2026-03",
            }
        }
        active = [
            {
                **desired["CASE-OA-OFFSET-oa-1"],
                "relation_mode": "oa_invoice_offset_auto_match",
                "status": "active",
            }
        ]
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            desired_relations=desired,
            active_relations=active,
        )

        changed = executor.sync({})

        self.assertFalse(changed)
        self.assertEqual(command_service.confirm_calls, [])
        self.assertEqual(command_service.cancel_calls, [])
        self.assertEqual(persist_calls, [])
        self.assertEqual(lifecycle_calls, [])

    def test_sync_confirms_missing_desired_relation_and_emits_scope(self) -> None:
        desired = {
            "CASE-OA-OFFSET-oa-1": {
                "case_id": "CASE-OA-OFFSET-oa-1",
                "row_ids": ["oa-1", "inv-1"],
                "row_types": ["oa", "invoice"],
                "month_scope": "2026-03",
                "amount_check": {"status": "matched", "invoice_total": "600.00", "oa_total": "600.00"},
            }
        }
        executor, command_service, persist_calls, lifecycle_calls = self._executor(desired_relations=desired)

        changed = executor.sync({})

        self.assertTrue(changed)
        self.assertEqual(command_service.confirm_calls[0]["case_id"], "CASE-OA-OFFSET-oa-1")
        self.assertEqual(command_service.confirm_calls[0]["actor_id"], "system_auto_match")
        self.assertEqual(
            command_service.confirm_calls[0]["amount_check"],
            {"status": "matched", "invoice_total": "600.00", "oa_total": "600.00"},
        )
        self.assertEqual(command_service.confirm_calls[0]["history_operation_type"], "oa_invoice_offset_auto_pair")
        self.assertEqual(persist_calls, [{"changed_case_ids": ["CASE-OA-OFFSET-oa-1"]}])
        self.assertEqual(lifecycle_calls[0]["event_name"], "pair_relation_changed")
        self.assertEqual(set(lifecycle_calls[0]["scope_keys"]), {"all", "2026-03"})

    def test_sync_updates_existing_relation_when_amount_check_is_missing(self) -> None:
        desired = {
            "CASE-OA-OFFSET-oa-1": {
                "case_id": "CASE-OA-OFFSET-oa-1",
                "row_ids": ["oa-1", "inv-1"],
                "row_types": ["oa", "invoice"],
                "month_scope": "2026-03",
                "amount_check": {"status": "matched", "invoice_total": "600.00", "oa_total": "600.00"},
            }
        }
        active = [
            {
                **desired["CASE-OA-OFFSET-oa-1"],
                "relation_mode": "oa_invoice_offset_auto_match",
                "status": "active",
                "amount_check": {},
            }
        ]
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            desired_relations=desired,
            active_relations=active,
        )

        changed = executor.sync({})

        self.assertTrue(changed)
        self.assertEqual(len(command_service.confirm_calls), 1)
        self.assertEqual(
            command_service.confirm_calls[0]["amount_check"],
            {"status": "matched", "invoice_total": "600.00", "oa_total": "600.00"},
        )
        self.assertEqual(command_service.confirm_calls[0]["before_relations"], active)
        self.assertTrue(command_service.confirm_calls[0]["replace_existing"])
        self.assertEqual(persist_calls, [{"changed_case_ids": ["CASE-OA-OFFSET-oa-1"]}])
        self.assertEqual(lifecycle_calls[0]["event_name"], "pair_relation_changed")

    def test_sync_cancels_stale_active_relation_only_when_current_payload_intersects(self) -> None:
        active = [
            {
                "case_id": "CASE-OA-OFFSET-oa-1",
                "row_ids": ["oa-1", "inv-1"],
                "relation_mode": "oa_invoice_offset_auto_match",
                "month_scope": "2026-03",
                "status": "active",
            }
        ]
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            desired_relations={},
            active_relations=active,
            scanned_row_ids={"oa-1"},
        )

        changed = executor.sync({})

        self.assertTrue(changed)
        self.assertEqual(command_service.cancel_calls[0]["case_id"], "CASE-OA-OFFSET-oa-1")
        self.assertEqual(
            command_service.cancel_calls[0]["history_operation_type"],
            "oa_invoice_offset_auto_pair_removed",
        )
        self.assertEqual(persist_calls, [{"changed_case_ids": ["CASE-OA-OFFSET-oa-1"]}])
        self.assertEqual(set(lifecycle_calls[0]["scope_keys"]), {"all", "2026-03"})

    def test_sync_does_not_cancel_relation_outside_current_payload(self) -> None:
        active = [
            {
                "case_id": "CASE-OA-OFFSET-other",
                "row_ids": ["oa-other", "inv-other"],
                "relation_mode": "oa_invoice_offset_auto_match",
                "month_scope": "2026-04",
                "status": "active",
            }
        ]
        executor, command_service, persist_calls, lifecycle_calls = self._executor(
            desired_relations={},
            active_relations=active,
            scanned_row_ids={"oa-current"},
        )

        changed = executor.sync({})

        self.assertFalse(changed)
        self.assertEqual(command_service.cancel_calls, [])
        self.assertEqual(persist_calls, [])
        self.assertEqual(lifecycle_calls, [])


if __name__ == "__main__":
    unittest.main()
