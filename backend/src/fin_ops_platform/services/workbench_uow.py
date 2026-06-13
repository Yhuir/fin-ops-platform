from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
    WorkbenchIdempotencyFailed,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
    WorkbenchIdempotencyRecord,
    WorkbenchIdempotencyReservation,
    is_workbench_idempotency_reserved_expired,
    workbench_request_fingerprint,
)
from fin_ops_platform.services.workbench_stale_precondition import assert_workbench_stale_preconditions
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
                existing_record = _idempotency_record(existing)
                _raise_on_fingerprint_conflict(existing_record, idempotency)
                _raise_if_idempotency_failed(existing_record, idempotency)
                replayed = _replay_committed_idempotency_response(existing_record)
                if replayed is not None:
                    return replayed
                _raise_if_idempotency_in_progress(existing_record, idempotency)

        with self._connection.transaction() as transaction:
            assert_workbench_stale_preconditions(command)
            idempotency_store = _transaction_bound_idempotency_store(self._idempotency_store, transaction)

            if idempotency is not None:
                reserved = _idempotency_reserve(idempotency_store, idempotency)
                if reserved is not None:
                    reserved_record = _idempotency_record(reserved)
                    _raise_on_fingerprint_conflict(reserved_record, idempotency)
                    _raise_if_idempotency_failed(reserved_record, idempotency)
                    replayed = _replay_committed_idempotency_response(reserved_record)
                    if replayed is not None:
                        return replayed
                    if _is_existing_reservation(reserved) and not _is_taken_over_expired_reservation(reserved):
                        _raise_if_idempotency_in_progress(reserved_record, idempotency)

            repositories = self._repository_factory(transaction)
            context = WorkbenchWriteUnitOfWorkContext(
                transaction=transaction,
                pair_relations=repositories.pair_relations,
                exception_cases=repositories.exception_cases,
                row_overrides=repositories.row_overrides,
                candidate_matches=repositories.candidate_matches,
                idempotency_store=idempotency_store,
            )
            handler_result = handler(context)
            if not isinstance(handler_result, dict):
                raise TypeError("WorkbenchWriteUnitOfWork handler must return a dict result.")

            result = dict(handler_result)
            source_versions: dict[str, Any] = {}
            outbox_event_ids: list[Any] = []
            for scope_key in _scope_keys_for(command, result):
                action_name = str(getattr(command, "action_name", "") or "")
                event = self._read_model_refresh_writer.enqueue_refresh(
                    transaction=transaction,
                    scope_type="workbench",
                    scope_key=scope_key,
                    reason=action_name,
                    metadata={"action_name": action_name} if action_name else None,
                )
                source_versions[scope_key] = _event_value(event, "source_version")
                outbox_event_ids.append(_event_value(event, "event_id"))

            result["source_versions"] = source_versions
            result["outbox_event_ids"] = outbox_event_ids
            if idempotency is not None:
                _idempotency_commit(
                    idempotency_store,
                    idempotency,
                    result,
                    source_versions=source_versions,
                    outbox_event_ids=outbox_event_ids,
                )
            return result

    def replay_committed(self, command: Any) -> dict[str, Any] | None:
        idempotency = _idempotency_request_for(command)
        if idempotency is None:
            return None
        existing = _idempotency_get(self._idempotency_store, idempotency)
        if existing is None:
            return None
        existing_record = _idempotency_record(existing)
        _raise_on_fingerprint_conflict(existing_record, idempotency)
        _raise_if_idempotency_failed(existing_record, idempotency)
        _raise_if_idempotency_in_progress(existing_record, idempotency)
        return _replay_committed_idempotency_response(existing_record)


class RuntimeQueueReadModelRefreshWriter:
    def __init__(
        self,
        queue_repository: Any,
        *,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
    ) -> None:
        self._queue_repository = queue_repository
        self._tenant_id = str(tenant_id or "default")
        self._priority = str(priority or "normal")
        self._trace_id = str(trace_id).strip() if trace_id else None

    def enqueue_refresh(
        self,
        *,
        transaction: Any,
        scope_type: str,
        scope_key: str,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> Any:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh_in_transaction", None)
        if not callable(enqueue):
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh_in_transaction.")
        return enqueue(
            transaction=transaction,
            scope_type=scope_type,
            scope_key=scope_key,
            reason=reason,
            tenant_id=self._tenant_id,
            priority=self._priority,
            trace_id=self._trace_id,
            metadata=metadata,
        )


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


def _transaction_bound_idempotency_store(store: Any, transaction: Any) -> Any:
    for_transaction = getattr(store, "for_transaction", None)
    if callable(for_transaction):
        return for_transaction(transaction)
    return store


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


def _idempotency_reserve(store: Any, request: _IdempotencyRequest) -> Any:
    reserve = getattr(store, "reserve", None)
    if not callable(reserve):
        return None
    try:
        return reserve(
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            request_payload=request.request_payload,
        )
    except TypeError:
        pass
    try:
        return reserve(
            request.idempotency_key,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            action_name=request.action_name,
            request_fingerprint=request.request_fingerprint,
            request_payload=request.request_payload,
        )
    except TypeError:
        return reserve(request.idempotency_key)


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


def _raise_if_idempotency_in_progress(existing: Any, request: _IdempotencyRequest) -> None:
    status = _record_value(existing, "status")
    if status != "reserved":
        return
    if is_workbench_idempotency_reserved_expired(existing):
        return
    raise WorkbenchIdempotencyInProgress(
        idempotency_key=request.idempotency_key,
        action_name=request.action_name,
    )


def _raise_if_idempotency_failed(existing: Any, request: _IdempotencyRequest) -> None:
    status = _record_value(existing, "status")
    if status != "failed":
        return
    raise WorkbenchIdempotencyFailed(
        idempotency_key=request.idempotency_key,
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


def _idempotency_record(value: Any) -> Any:
    if isinstance(value, WorkbenchIdempotencyReservation):
        return value.record
    record = getattr(value, "record", None)
    if record is not None and hasattr(value, "created"):
        return record
    return value


def _is_existing_reservation(value: Any) -> bool:
    if isinstance(value, WorkbenchIdempotencyReservation):
        return not value.created
    if hasattr(value, "record") and hasattr(value, "created"):
        return not bool(getattr(value, "created"))
    return False


def _is_taken_over_expired_reservation(value: Any) -> bool:
    if isinstance(value, WorkbenchIdempotencyReservation):
        return value.taken_over_expired
    return bool(getattr(value, "taken_over_expired", False))


def _record_value(record: Any, name: str) -> Any:
    if isinstance(record, WorkbenchIdempotencyRecord):
        return getattr(record, name)
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)
