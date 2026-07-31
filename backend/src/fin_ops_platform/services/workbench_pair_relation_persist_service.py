from __future__ import annotations

from threading import Lock
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchPairRelationPersistService:
    def __init__(
        self,
        *,
        pair_relation_service: WorkbenchPairRelationService,
        state_store: Any | None,
        clear_search_cache: Callable[[], None],
        emit_action_timing: Callable[..., None],
        duration_ms: Callable[[float], int],
        monotonic_clock: Callable[[], float] = monotonic,
        initial_version: int = 0,
        initial_pending_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        self._pair_relation_service = pair_relation_service
        self._state_store = state_store
        self._clear_search_cache = clear_search_cache
        self._emit_action_timing = emit_action_timing
        self._duration_ms = duration_ms
        self._monotonic_clock = monotonic_clock
        self._version = int(initial_version or 0)
        self._pending_case_ids: set[str] = set(self._normalize_case_ids(initial_pending_case_ids))
        self._lock = Lock()

    @property
    def version(self) -> int:
        return self._version

    @property
    def pending_case_ids(self) -> set[str]:
        return set(self._pending_case_ids)

    def force_state(
        self,
        *,
        version: int,
        pending_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        with self._lock:
            self._version = int(version or 0)
            self._pending_case_ids = set(self._normalize_case_ids(pending_case_ids))

    def persist(self, *, changed_case_ids: list[str] | None = None) -> None:
        self._clear_search_cache()
        if self._state_store is None:
            return
        snapshot = (
            self._pair_relation_service.snapshot_case_ids(changed_case_ids)
            if changed_case_ids is not None
            else self._pair_relation_service.snapshot()
        )
        self._state_store.save_workbench_pair_relations(
            snapshot,
            changed_case_ids=changed_case_ids,
        )

    def schedule(
        self,
        *,
        changed_case_ids: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        normalized_case_ids = self._normalize_case_ids(changed_case_ids)
        if not normalized_case_ids:
            return
        with self._lock:
            self._pending_case_ids.update(normalized_case_ids)
            self._version += 1
            version = self._version
        self.persist_pending(
            version=version,
            case_ids=normalized_case_ids,
            request_id=request_id,
            action_name=action_name,
        )

    def persist_pending(
        self,
        *,
        version: int,
        case_ids: list[str],
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        with self._lock:
            if int(version or 0) != self._version:
                return
            pending_case_ids = sorted(self._pending_case_ids)
            self._pending_case_ids.clear()
        case_ids_to_persist = pending_case_ids or self._normalize_case_ids(case_ids)
        if not case_ids_to_persist:
            return
        persist_started_at = self._monotonic_clock()
        self.persist(changed_case_ids=case_ids_to_persist)
        if request_id is not None and action_name is not None:
            self._emit_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="persist_pair_relations",
                duration_ms=self._duration_ms(persist_started_at),
                detail=",".join(case_ids_to_persist),
            )

    @staticmethod
    def _normalize_case_ids(case_ids: set[str] | list[str] | None) -> list[str]:
        return [
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        ]
