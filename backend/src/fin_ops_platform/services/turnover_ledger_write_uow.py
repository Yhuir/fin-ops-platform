from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.workbench_uow import (
    _idempotency_commit,
    _idempotency_get,
    _idempotency_record,
    _idempotency_request_for,
    _idempotency_reserve,
    _is_existing_reservation,
    _is_taken_over_expired_reservation,
    _raise_if_idempotency_failed,
    _raise_if_idempotency_in_progress,
    _raise_on_fingerprint_conflict,
    _replay_committed_idempotency_response,
    _transaction_bound_idempotency_store,
)


@dataclass(frozen=True)
class TurnoverLedgerWriteContext:
    command: Any
    transaction: Any
    relation_repository: Any
    extra_repository: Any
    settings_port: Any
    bankdetail_port: Any
    workbench_pair_port: Any


class TurnoverLedgerWriteUnitOfWork:
    def __init__(
        self,
        *,
        connection: Any,
        relation_repository: Any,
        extra_repository: Any,
        settings_port: Any,
        bankdetail_port: Any,
        dirty_outbox_writer: Any,
        stale_precondition_port: Any,
        idempotency_store: Any | None = None,
        workbench_pair_port: Any | None = None,
    ) -> None:
        self._connection = connection
        self._relation_repository = relation_repository
        self._extra_repository = extra_repository
        self._settings_port = settings_port
        self._bankdetail_port = bankdetail_port
        self._dirty_outbox_writer = dirty_outbox_writer
        self._stale_precondition_port = stale_precondition_port
        self._idempotency_store = idempotency_store
        self._workbench_pair_port = workbench_pair_port

    def run(self, command: Any, handler: Callable[[TurnoverLedgerWriteContext], Any]) -> Any:
        idempotency = _idempotency_request_for(command) if self._idempotency_store is not None else None
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
            expected_versions = dict(getattr(command, "expected_versions", {}) or {})
            if expected_versions:
                self._stale_precondition_port.assert_current(
                    expected_versions=expected_versions,
                    transaction=transaction,
                )
            idempotency_store = (
                _transaction_bound_idempotency_store(self._idempotency_store, transaction)
                if self._idempotency_store is not None
                else None
            )
            if idempotency is not None and idempotency_store is not None:
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

            context = TurnoverLedgerWriteContext(
                command=command,
                transaction=transaction,
                relation_repository=self._relation_repository,
                extra_repository=self._extra_repository,
                settings_port=self._settings_port,
                bankdetail_port=self._bankdetail_port,
                workbench_pair_port=self._workbench_pair_port,
            )
            result = handler(context)
            refresh_requests = list(getattr(command, "refresh_requests", []) or [])
            if not refresh_requests:
                refresh_requests = [
                    {
                        "scope_type": "turnover_ledger",
                        "scope_keys": list(getattr(command, "scope_keys", []) or ["all"]),
                        "reason": str(getattr(command, "action_name", "") or "turnover_ledger_write"),
                    }
                ]
            source_versions: dict[str, Any] = {}
            outbox_event_ids: list[Any] = []
            result_refresh_metadata = _result_refresh_metadata(result)
            prepared_refreshes: list[dict[str, object]] = []
            for refresh_request in refresh_requests:
                request = dict(refresh_request)
                request_metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
                refresh_metadata = _merge_refresh_metadata(request_metadata, result_refresh_metadata)
                prepared_refreshes.append(
                    {
                        "scope_type": str(request.get("scope_type") or "turnover_ledger"),
                        "scope_keys": list(request.get("scope_keys") or ["all"]),
                        "reason": str(
                            request.get("reason")
                            or getattr(command, "action_name", "")
                            or "turnover_ledger_write"
                        ),
                        "payload": {
                            "tenant_id": getattr(command, "tenant_id", None),
                            "actor_id": getattr(command, "actor_id", None),
                            "action_name": getattr(command, "action_name", None),
                            **refresh_metadata,
                        },
                    }
                )
            events = self._dirty_outbox_writer.enqueue_refreshes(
                transaction=transaction,
                refreshes=prepared_refreshes,
            )
            for event in list(events or []):
                event_id = _event_value(event, "event_id")
                source_version = _event_value(event, "source_version")
                if event_id is not None:
                    outbox_event_ids.append(event_id)
                if source_version is not None:
                    event_scope_key = _event_value(event, "scope_key")
                    if event_scope_key is not None:
                        source_versions[str(event_scope_key)] = source_version
            if idempotency is not None and idempotency_store is not None:
                if not isinstance(result, dict):
                    raise TypeError("TurnoverLedgerWriteUnitOfWork idempotent handler must return a dict result.")
                result = dict(result)
                result["source_versions"] = dict(source_versions)
                result["outbox_event_ids"] = list(outbox_event_ids)
                _idempotency_commit(
                    idempotency_store,
                    idempotency,
                    result,
                    source_versions=source_versions,
                    outbox_event_ids=outbox_event_ids,
                )
            return result


def _event_value(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _result_refresh_metadata(result: Any) -> dict[str, object]:
    if not isinstance(result, dict):
        return {}
    pair_relation = result.get("workbench_pair_relation")
    pair_relation = pair_relation if isinstance(pair_relation, dict) else {}
    relation = result.get("relation")
    relation = relation if isinstance(relation, dict) else {}
    row_ids = _metadata_text_list(
        [
            *_metadata_text_list(pair_relation.get("row_ids")),
            *_metadata_text_list(relation.get("row_ids")),
            *_metadata_text_list(relation.get("bank_row_ids")),
        ]
    )
    case_id = str(pair_relation.get("case_id") or "").strip()
    relation_status = str(pair_relation.get("status") or "").strip().lower()
    relation_deltas = (
        {case_id: {"status": relation_status, "row_ids": row_ids}}
        if case_id and row_ids and relation_status in {"active", "cancelled"}
        else {}
    )
    return {
        **({"row_ids": row_ids} if row_ids else {}),
        **({"case_ids": [case_id]} if case_id else {}),
        **({"relation_deltas": relation_deltas} if relation_deltas else {}),
    }


def _merge_refresh_metadata(*items: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for name in ("row_ids", "case_ids"):
            merged = _metadata_text_list([*list(result.get(name) or []), *_metadata_text_list(item.get(name))])
            if merged:
                result[name] = merged
        relation_deltas = item.get("relation_deltas")
        if isinstance(relation_deltas, dict):
            existing_deltas = result.get("relation_deltas")
            result["relation_deltas"] = {
                **(dict(existing_deltas) if isinstance(existing_deltas, dict) else {}),
                **dict(relation_deltas),
            }
    return result


def _metadata_text_list(value: object) -> list[str]:
    raw_items = [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple, set)) else []
    result: list[str] = []
    for item in raw_items:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result
