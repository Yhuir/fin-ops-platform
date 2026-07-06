from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
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
from fin_ops_platform.services.read_model_scope_policy import DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY
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


@dataclass(frozen=True)
class WorkbenchReadModelRefreshTarget:
    scope_type: str
    scope_key: str
    reason: str
    metadata: dict[str, object] | None = None


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
        uow_started_at = monotonic()
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
            handler_started_at = monotonic()
            handler_result = handler(context)
            if not isinstance(handler_result, dict):
                raise TypeError("WorkbenchWriteUnitOfWork handler must return a dict result.")
            _emit_timing_if_available(
                command,
                "uow_handler",
                handler_started_at,
                detail=f"result_keys={len(handler_result)}",
            )

            result = dict(handler_result)
            source_versions: dict[str, Any] = {}
            outbox_event_ids: list[Any] = []
            target_started_at = monotonic()
            refresh_targets = _refresh_targets_for(command, result)
            _emit_timing_if_available(
                command,
                "uow_refresh_target_plan",
                target_started_at,
                detail=f"target_count={len(refresh_targets)}",
            )
            enqueue_started_at = monotonic()
            refresh_events = self._enqueue_refresh_targets(transaction=transaction, targets=refresh_targets)
            _emit_timing_if_available(
                command,
                "uow_enqueue_refresh_targets",
                enqueue_started_at,
                detail=f"target_count={len(refresh_targets)}",
            )
            if len(refresh_events) != len(refresh_targets):
                raise RuntimeError("read model refresh writer returned a different number of events than targets.")
            for target, event in zip(refresh_targets, refresh_events, strict=True):
                source_version_key = (
                    target.scope_key
                    if target.scope_type == "workbench"
                    else f"{target.scope_type}:{target.scope_key}"
                )
                source_versions[source_version_key] = _event_value(event, "source_version")
                outbox_event_ids.append(_event_value(event, "event_id"))

            result["source_versions"] = source_versions
            result["outbox_event_ids"] = outbox_event_ids
            if idempotency is not None:
                commit_started_at = monotonic()
                _idempotency_commit(
                    idempotency_store,
                    idempotency,
                    result,
                    source_versions=source_versions,
                    outbox_event_ids=outbox_event_ids,
                )
                _emit_timing_if_available(
                    command,
                    "uow_idempotency_commit",
                    commit_started_at,
                    detail=f"outbox_count={len(outbox_event_ids)}",
                )
            _emit_timing_if_available(
                command,
                "uow_total",
                uow_started_at,
                detail=f"outbox_count={len(outbox_event_ids)}",
            )
            return result

    def _enqueue_refresh_targets(
        self,
        *,
        transaction: Any,
        targets: list[WorkbenchReadModelRefreshTarget],
    ) -> list[Any]:
        enqueue_many = getattr(self._read_model_refresh_writer, "enqueue_refreshes", None)
        if callable(enqueue_many):
            return list(
                enqueue_many(
                    transaction=transaction,
                    targets=[
                        {
                            "scope_type": target.scope_type,
                            "scope_key": target.scope_key,
                            "reason": target.reason,
                            "metadata": dict(target.metadata) if target.metadata is not None else None,
                        }
                        for target in targets
                    ],
                )
            )
        events: list[Any] = []
        for target in targets:
            events.append(
                self._read_model_refresh_writer.enqueue_refresh(
                    transaction=transaction,
                    scope_type=target.scope_type,
                    scope_key=target.scope_key,
                    reason=target.reason,
                    metadata=dict(target.metadata) if target.metadata is not None else None,
                )
            )
        return events

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

    def enqueue_refreshes(
        self,
        *,
        transaction: Any,
        targets: list[dict[str, object]],
    ) -> list[Any]:
        enqueue_many = getattr(self._queue_repository, "enqueue_read_model_refreshes_in_transaction", None)
        if callable(enqueue_many):
            return list(
                enqueue_many(
                    transaction=transaction,
                    refreshes=list(targets or []),
                    tenant_id=self._tenant_id,
                    priority=self._priority,
                    trace_id=self._trace_id,
                )
            )
        return [
            self.enqueue_refresh(
                transaction=transaction,
                scope_type=str(target.get("scope_type") or ""),
                scope_key=str(target.get("scope_key") or ""),
                reason=str(target.get("reason") or ""),
                metadata=dict(target.get("metadata") or {}) if isinstance(target.get("metadata"), dict) else None,
            )
            for target in list(targets or [])
            if isinstance(target, dict)
        ]


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


def _refresh_targets_for(command: Any, handler_result: dict[str, Any]) -> list[WorkbenchReadModelRefreshTarget]:
    action_name = str(getattr(command, "action_name", "") or "")
    reason = _refresh_reason_for(command, action_name)
    metadata = _refresh_metadata_for(command, action_name, handler_result)
    scope_keys = _scope_keys_for(command, handler_result)
    targets: list[WorkbenchReadModelRefreshTarget] = []

    _extend_refresh_targets(
        targets,
        scope_type="workbench",
        scope_keys=scope_keys,
        reason=reason,
        metadata=metadata,
    )
    if reason != "workbench_relation_changed":
        return targets

    _extend_refresh_targets(
        targets,
        scope_type="workbench_relation",
        scope_keys=scope_keys,
        reason="workbench_pair_relation_changed",
        metadata=metadata,
    )
    downstream_scope_types = _metadata_text_set(metadata, "downstream_scope_types")
    for scope_type in (
        "bank_detail",
        "invoice_lifecycle",
        "input_invoice_usage",
        "output_invoice_collection",
        "oa_pending_payment",
        "search",
        "tax_offset",
        "no_oa_bank_batch",
        "bank_flow_rule_batch",
    ):
        if scope_type in downstream_scope_types:
            _extend_refresh_targets(
                targets,
                scope_type=scope_type,
                scope_keys=scope_keys,
                reason=reason,
                metadata=metadata,
            )
    if "cost_statistics" in downstream_scope_types:
        _extend_refresh_targets(
            targets,
            scope_type="cost_statistics",
            scope_keys=scope_keys,
            reason=reason,
            metadata=metadata,
        )
    if "pending_invoice" in downstream_scope_types:
        _extend_refresh_targets(
            targets,
            scope_type="pending_invoice",
            scope_keys=_metadata_text_list(metadata, "pending_invoice_scope_keys"),
            reason=reason,
            metadata=metadata,
        )
    return _dedupe_refresh_targets(targets)


def _extend_refresh_targets(
    targets: list[WorkbenchReadModelRefreshTarget],
    *,
    scope_type: str,
    scope_keys: list[str],
    reason: str,
    metadata: dict[str, object] | None,
) -> None:
    for scope_key in _normalize_refresh_scope_keys(scope_type, scope_keys):
        targets.append(
            WorkbenchReadModelRefreshTarget(
                scope_type=scope_type,
                scope_key=scope_key,
                reason=reason,
                metadata=metadata,
            )
        )


def _normalize_refresh_scope_keys(scope_type: str, scope_keys: list[str]) -> list[str]:
    return DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY.normalize_and_validate(scope_type, scope_keys)


def _dedupe_refresh_targets(targets: list[WorkbenchReadModelRefreshTarget]) -> list[WorkbenchReadModelRefreshTarget]:
    result: list[WorkbenchReadModelRefreshTarget] = []
    seen: set[tuple[str, str, str]] = set()
    for target in targets:
        key = (target.scope_type, target.scope_key, target.reason)
        if key in seen:
            continue
        seen.add(key)
        result.append(target)
    return result


def _metadata_text_list(metadata: dict[str, object] | None, name: str) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    raw_value = metadata.get(name)
    if isinstance(raw_value, str):
        raw_items: list[object] = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_items = list(raw_value)
    else:
        return []
    return [item for item in (str(raw_item or "").strip() for raw_item in raw_items) if item]


def _metadata_text_set(metadata: dict[str, object] | None, name: str) -> set[str]:
    return set(_metadata_text_list(metadata, name))


def _refresh_metadata_for(
    command: Any,
    action_name: str,
    handler_result: dict[str, Any] | None = None,
) -> dict[str, object] | None:
    raw_metadata = getattr(command, "refresh_metadata", None)
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    result_metadata = handler_result.get("refresh_metadata") if isinstance(handler_result, dict) else None
    if isinstance(result_metadata, dict):
        metadata.update(result_metadata)
    if action_name:
        metadata["action_name"] = action_name
    return metadata or None


def _refresh_reason_for(command: Any, action_name: str) -> str:
    raw_metadata = getattr(command, "refresh_metadata", None)
    if isinstance(raw_metadata, dict):
        explicit_reason = str(raw_metadata.get("refresh_reason") or "").strip()
        if explicit_reason:
            return explicit_reason
    if action_name in {"confirm_link", "withdraw_link", "cancel_link"}:
        return "workbench_relation_changed"
    return action_name or "workbench_write_changed"


def _emit_timing_if_available(command: Any, phase: str, started_at: float, *, detail: str | None = None) -> None:
    emitter = getattr(command, "timing_emit", None)
    if not callable(emitter):
        return
    emitter(phase, started_at, detail)


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
