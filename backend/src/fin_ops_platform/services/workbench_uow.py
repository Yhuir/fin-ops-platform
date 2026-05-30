from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
    WorkbenchIdempotencyKeyConflict,
    WorkbenchIdempotencyRecord,
    workbench_request_fingerprint,
)
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


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
        idempotency = _idempotency_request_for(command)
        if idempotency is not None:
            existing = _idempotency_get(self._idempotency_store, idempotency)
            if existing is not None:
                _raise_on_fingerprint_conflict(existing, idempotency)
                replayed = _replay_committed_idempotency_response(existing)
                if replayed is not None:
                    return replayed

        with self._connection.transaction() as transaction:
            if idempotency is not None:
                _idempotency_reserve(self._idempotency_store, idempotency)

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
            if idempotency is not None:
                _idempotency_commit(
                    self._idempotency_store,
                    idempotency,
                    result,
                    source_versions=source_versions,
                    outbox_event_ids=outbox_event_ids,
                )
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


@dataclass(frozen=True)
class _IdempotencyRequest:
    tenant_id: str
    actor_id: str
    action_name: str
    idempotency_key: str
    request_fingerprint: str
    request_payload: dict[str, Any]


def _idempotency_request_for(command: Any) -> _IdempotencyRequest | None:
    idempotency_key = str(getattr(command, "idempotency_key", "") or "").strip()
    if not idempotency_key:
        return None

    tenant_id = str(getattr(command, "tenant_id", "") or "default")
    actor_id = str(getattr(command, "actor_id", "") or "system")
    action_name = str(getattr(command, "action_name", "") or "")
    request_payload = getattr(command, "payload", None)
    if not isinstance(request_payload, dict):
        request_payload = {}
    request_fingerprint = str(getattr(command, "request_fingerprint", "") or "").strip()
    if not request_fingerprint:
        request_fingerprint = workbench_request_fingerprint(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action_name=action_name,
            payload=request_payload,
        )
    return _IdempotencyRequest(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action_name=action_name,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        request_payload=dict(request_payload),
    )


def _idempotency_get(store: Any, request: _IdempotencyRequest) -> Any:
    get_committed_or_reserved = getattr(store, "get_committed_or_reserved", None)
    if callable(get_committed_or_reserved):
        return get_committed_or_reserved(request.tenant_id, request.actor_id, request.idempotency_key)

    get = getattr(store, "get", None)
    if not callable(get):
        return None
    try:
        return get(
            request.idempotency_key,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
        )
    except TypeError:
        return get(request.idempotency_key)


def _idempotency_reserve(store: Any, request: _IdempotencyRequest) -> None:
    reserve = getattr(store, "reserve", None)
    if not callable(reserve):
        return
    try:
        reserve(
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            request_payload=request.request_payload,
        )
        return
    except TypeError:
        pass
    try:
        reserve(
            request.idempotency_key,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            request_fingerprint=request.request_fingerprint,
            request_payload=request.request_payload,
        )
    except TypeError:
        reserve(request.idempotency_key)


def _idempotency_commit(
    store: Any,
    request: _IdempotencyRequest,
    result: dict[str, Any],
    *,
    source_versions: dict[str, Any],
    outbox_event_ids: list[Any],
) -> None:
    commit = getattr(store, "commit", None)
    if not callable(commit):
        return
    try:
        commit(
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            response_payload=dict(result),
            source_versions=dict(source_versions),
            outbox_event_ids=list(outbox_event_ids),
        )
        return
    except TypeError:
        pass
    try:
        commit(
            request.idempotency_key,
            dict(result),
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            request_fingerprint=request.request_fingerprint,
            source_versions=dict(source_versions),
            outbox_event_ids=list(outbox_event_ids),
        )
    except TypeError:
        commit(request.idempotency_key, dict(result))


def _raise_on_fingerprint_conflict(existing: Any, request: _IdempotencyRequest) -> None:
    existing_fingerprint = _record_value(existing, "request_fingerprint")
    if existing_fingerprint is None or str(existing_fingerprint) == request.request_fingerprint:
        return
    raise WorkbenchIdempotencyKeyConflict(
        idempotency_key=request.idempotency_key,
        existing_fingerprint=str(existing_fingerprint),
        incoming_fingerprint=request.request_fingerprint,
        action_name=request.action_name,
    )


def _replay_committed_idempotency_response(existing: Any) -> dict[str, Any] | None:
    status = _record_value(existing, "status")
    if status is not None and status != "committed":
        return None

    response_payload = _record_value(existing, "response_payload")
    if response_payload is None and isinstance(existing, dict) and status is None:
        response_payload = existing
    if not isinstance(response_payload, dict):
        return None

    result = dict(response_payload)
    source_versions = _record_value(existing, "source_versions")
    outbox_event_ids = _record_value(existing, "outbox_event_ids")
    if source_versions is not None:
        result["source_versions"] = dict(source_versions)
    if outbox_event_ids is not None:
        result["outbox_event_ids"] = list(outbox_event_ids)
    return result


def _record_value(record: Any, name: str) -> Any:
    if isinstance(record, WorkbenchIdempotencyRecord):
        return getattr(record, name)
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)
