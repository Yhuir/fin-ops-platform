from __future__ import annotations

import unittest
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_persist_service import WorkbenchPairRelationPersistService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class StateStoreStub:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        self.saved.append(
            {
                "snapshot": snapshot,
                "changed_case_ids": list(changed_case_ids or []) if changed_case_ids is not None else None,
            }
        )


class CapturedThread:
    started: list[dict[str, Any]] = []

    def __init__(self, *, target, kwargs: dict[str, Any], daemon: bool) -> None:
        self._target = target
        self._kwargs = kwargs
        self._daemon = daemon

    def start(self) -> None:
        self.started.append({"target": self._target, "kwargs": dict(self._kwargs), "daemon": self._daemon})


class WorkbenchPairRelationPersistServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        CapturedThread.started = []

    def test_persist_clears_cache_and_saves_changed_case_snapshot(self) -> None:
        state_store = StateStoreStub()
        clear_calls: list[str] = []
        service = WorkbenchPairRelationPersistService(
            pair_relation_service=self._pair_relation_service(),
            state_store=state_store,
            clear_search_cache=lambda: clear_calls.append("clear"),
            emit_action_timing=lambda **_: None,
            duration_ms=lambda _: 0,
        )

        service.persist(changed_case_ids=["CASE-001"])

        self.assertEqual(clear_calls, ["clear"])
        self.assertEqual(state_store.saved[0]["changed_case_ids"], ["CASE-001"])
        self.assertEqual(
            sorted(state_store.saved[0]["snapshot"]["pair_relations"].keys()),
            ["CASE-001"],
        )

    def test_schedule_coalesces_pending_case_ids_when_async_workers_overlap(self) -> None:
        state_store = StateStoreStub()
        service = WorkbenchPairRelationPersistService(
            pair_relation_service=self._pair_relation_service(),
            state_store=state_store,
            clear_search_cache=lambda: None,
            emit_action_timing=lambda **_: None,
            duration_ms=lambda _: 0,
            async_enabled=lambda: True,
            thread_factory=CapturedThread,
        )

        service.schedule(changed_case_ids=["CASE-001"], action_name="confirm_link")
        service.schedule(changed_case_ids=["CASE-002"], action_name="confirm_link")

        self.assertEqual(len(CapturedThread.started), 2)
        CapturedThread.started[0]["target"](**CapturedThread.started[0]["kwargs"])
        self.assertEqual(state_store.saved, [])

        CapturedThread.started[1]["target"](**CapturedThread.started[1]["kwargs"])

        self.assertEqual(state_store.saved[0]["changed_case_ids"], ["CASE-001", "CASE-002"])
        self.assertEqual(service.pending_case_ids, set())

    def test_schedule_persists_synchronously_when_async_disabled_and_emits_timing(self) -> None:
        state_store = StateStoreStub()
        timing_calls: list[dict[str, Any]] = []
        service = WorkbenchPairRelationPersistService(
            pair_relation_service=self._pair_relation_service(),
            state_store=state_store,
            clear_search_cache=lambda: None,
            emit_action_timing=lambda **kwargs: timing_calls.append(kwargs),
            duration_ms=lambda started_at: int(20 - started_at),
            async_enabled=lambda: False,
            monotonic_clock=lambda: 7.0,
        )

        service.schedule(
            changed_case_ids=["CASE-002"],
            request_id="req-001",
            action_name="confirm_link",
        )

        self.assertEqual(state_store.saved[0]["changed_case_ids"], ["CASE-002"])
        self.assertEqual(timing_calls[0]["phase"], "persist_pair_relations")
        self.assertEqual(timing_calls[0]["duration_ms"], 13)
        self.assertEqual(timing_calls[0]["detail"], "CASE-002")
        self.assertEqual(service.pending_case_ids, set())

    @staticmethod
    def _pair_relation_service() -> WorkbenchPairRelationService:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-001",
            row_ids=["txn-001", "oa-001"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-01",
        )
        service.create_active_relation(
            case_id="CASE-002",
            row_ids=["txn-002", "oa-002"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-01",
        )
        return service


if __name__ == "__main__":
    unittest.main()
