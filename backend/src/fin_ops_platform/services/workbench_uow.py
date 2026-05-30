from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
    WorkbenchIdempotencyKeyConflict,
    WorkbenchIdempotencyRecord,
    workbench_request_fingerprint,
)


@dataclass(frozen=True)
class WorkbenchWriteUnitOfWorkContext:
    transaction: Any
    pair_relations: Any
    exception_cases: Any
    row_overrides: Any
    candidate_matches: Any
    idempotency_store: Any


class WorkbenchWriteUnitOfWork:
    def __init__(
        self,
        *,
        connection: Any,
        repository_factory: Callable[[Any], Any],
        read_model_refresh_writer: Any,
        idempotency_store: Any,
    ) -> None:
        self._connection = connection
        self._repository_factory = repository_factory
        self._read_model_refresh_writer = read_model_refresh_writer
        self._idempotency_store = idempotency_store

    def run(
        self,
        command: Any,
        handler: Callable[[WorkbenchWriteUnitOfWorkContext], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._connection.transaction() as transaction:
            repositories = self._repository_factory(transaction)
            context = WorkbenchWriteUnitOfWorkContext(
                transaction=transaction,
                pair_relations=repositories.pair_relations,
                exception_cases=repositories.exception_cases,
                row_overrides=repositories.row_overrides,
                candidate_matches=repositories.candidate_matches,
                idempotency_store=self._idempotency_store,
            )
            handler_result = handler(context)
            if not isinstance(handler_result, dict):
                raise TypeError("WorkbenchWriteUnitOfWork handler must return a dict result.")

            result = dict(handler_result)
            source_versions: dict[str, Any] = {}
            outbox_event_ids: list[Any] = []
            for scope_key in _scope_keys_for(command, result):
                event = self._read_model_refresh_writer.enqueue_refresh(
                    transaction=transaction,
                    scope_type="workbench",
                    scope_key=scope_key,
                    reason=str(getattr(command, "action_name", "") or ""),
                )
                source_versions[scope_key] = _event_value(event, "source_version")
                outbox_event_ids.append(_event_value(event, "event_id"))

            result["source_versions"] = source_versions
            result["outbox_event_ids"] = outbox_event_ids
            return result


def _scope_keys_for(command: Any, handler_result: dict[str, Any]) -> list[str]:
    raw_scope_keys = getattr(command, "scope_keys", None) or handler_result.get("affected_scope_keys") or []
    scope_keys: list[str] = []
    seen: set[str] = set()
    for raw_scope_key in raw_scope_keys:
        scope_key = str(raw_scope_key).strip()
        if not scope_key or scope_key in seen:
            continue
        seen.add(scope_key)
        scope_keys.append(scope_key)
    return scope_keys


def _event_value(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event[name]
    return getattr(event, name)
