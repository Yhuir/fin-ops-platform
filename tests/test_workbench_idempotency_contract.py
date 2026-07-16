from __future__ import annotations

import importlib
import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from tests.app_test_support import (
    build_grouped_workbench_projection,
    build_local_state_application as build_application,
    install_fresh_workbench_write_gate,
)

from tests.test_workbench_uow_contract import (
    _Command,
    _RecordingConnection,
    _RecordingDirtyOutboxWriter,
    _RecordingRepositoryFactory,
)


"""
PF-P024/PF-P025 durable idempotency contracts.

PF-P025 turns the record, fingerprint, conflict, and in-memory repository
primitive contracts green. The remaining expected failures describe the future
UoW replay / reserve / commit integration, not a skipped test suite.
"""


class _OperationRecordingIdempotencyStore:
    def __init__(self, *, committed: dict[str, dict[str, object]] | None = None) -> None:
        self.committed = committed or {}
        self.operations: list[dict[str, object]] = []

    def get(self, key: str, **kwargs: object) -> dict[str, object] | None:
        self.operations.append({"op": "get", "key": key, **kwargs})
        return self.committed.get(key)

    def reserve(self, key: str, **kwargs: object) -> None:
        self.operations.append({"op": "reserve", "key": key, **kwargs})

    def commit(self, key: str, result: object, **kwargs: object) -> None:
        self.operations.append({"op": "commit", "key": key, "result": result, **kwargs})
        self.committed[key] = {"status": "committed", "response_payload": result}


class WorkbenchDurableIdempotencyContractTests(unittest.TestCase):
    def _uow_class(self) -> type:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        cls = getattr(module, "WorkbenchWriteUnitOfWork", None)
        if cls is None:
            self.fail("WorkbenchWriteUnitOfWork must exist before durable idempotency can be integrated.")
        return cls

    def _new_uow(
        self,
        *,
        connection: _RecordingConnection | None = None,
        idempotency_store: object | None = None,
        read_model_writer: _RecordingDirtyOutboxWriter | None = None,
    ) -> object:
        cls = self._uow_class()
        return cls(
            connection=connection or _RecordingConnection(),
            repository_factory=_RecordingRepositoryFactory(),
            read_model_refresh_writer=read_model_writer or _RecordingDirtyOutboxWriter(),
            idempotency_store=idempotency_store or _OperationRecordingIdempotencyStore(),
        )

    def _run_uow(self, uow: object, command: _Command, handler: Callable[[object], dict[str, object]]) -> dict[str, object]:
        run = getattr(uow, "run", None)
        if not callable(run):
            self.fail("WorkbenchWriteUnitOfWork must expose run(command, handler).")
        result = run(command, handler)
        if not isinstance(result, dict):
            self.fail("WorkbenchWriteUnitOfWork.run must return a dict response payload.")
        return result

    def test_idempotency_record_contract_exposes_required_fields_and_identity(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")

        record = record_class(
            tenant_id="default",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp-1",
            actor_id="finance-1",
            request_payload={"case_id": "CASE-1", "authorization": "Bearer SECRET"},
            response_payload={"case_id": "CASE-1", "affected_row_ids": ["oa-1"]},
            source_versions={"2026-05": 7},
            outbox_event_ids=["event-7"],
            status="committed",
        )

        self.assertEqual(record.unique_identity, ("default", "finance-1", "confirm:idem-1"))
        self.assertEqual(record.action_identity, ("default", "confirm_link", "confirm:idem-1"))
        self.assertEqual(record.request_fingerprint, "fp-1")
        self.assertEqual(record.source_versions, {"2026-05": 7})
        self.assertEqual(record.outbox_event_ids, ["event-7"])
        self.assertNotIn("SECRET", json.dumps(record.to_storage_payload(), sort_keys=True))

    def test_request_fingerprint_is_stable_for_json_order_and_excludes_trace_context(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        fingerprint = getattr(module, "workbench_request_fingerprint")

        first = fingerprint(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            payload={
                "case_id": "CASE-1",
                "row_ids": ["bank-1", "oa-1"],
                "trace_id": "trace-a",
                "request_started_at": "2026-05-30T01:00:00Z",
            },
        )
        second = fingerprint(
            action_name="confirm_link",
            actor_id="finance-1",
            tenant_id="default",
            payload={
                "request_started_at": "2026-05-30T01:01:00Z",
                "trace_id": "trace-b",
                "row_ids": ["bank-1", "oa-1"],
                "case_id": "CASE-1",
            },
        )
        different_actor = fingerprint(
            tenant_id="default",
            actor_id="finance-2",
            action_name="confirm_link",
            payload={"case_id": "CASE-1", "row_ids": ["bank-1", "oa-1"]},
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_actor)

    def test_same_key_different_fingerprint_maps_to_409_conflict_payload(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        conflict_class = getattr(module, "WorkbenchIdempotencyKeyConflict")

        conflict = conflict_class(
            idempotency_key="confirm:idem-1",
            existing_fingerprint="fp-old",
            incoming_fingerprint="fp-new",
            action_name="confirm_link",
        )
        payload = conflict.to_response_payload()

        self.assertEqual(getattr(conflict, "status_code", None), 409)
        self.assertEqual(payload["error"], "idempotency_key_conflict")
        self.assertEqual(payload["idempotency_key"], "confirm:idem-1")
        self.assertIn("same idempotency key", payload["message"].lower())

    def test_same_key_same_fingerprint_in_progress_maps_to_409_retryable_payload(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        in_progress_class = getattr(module, "WorkbenchIdempotencyInProgress")

        in_progress = in_progress_class(
            idempotency_key="confirm:idem-1",
            action_name="confirm_link",
        )
        payload = in_progress.to_response_payload()

        self.assertEqual(getattr(in_progress, "status_code", None), 409)
        self.assertEqual(payload["error"], "idempotency_key_in_progress")
        self.assertEqual(payload["idempotency_key"], "confirm:idem-1")
        self.assertEqual(payload["action_name"], "confirm_link")
        self.assertTrue(payload["retryable"])

    def test_same_key_same_fingerprint_failed_maps_to_409_non_retryable_payload(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        failed_class = getattr(module, "WorkbenchIdempotencyFailed")

        failed = failed_class(
            idempotency_key="confirm:idem-1",
            action_name="confirm_link",
        )
        payload = failed.to_response_payload()

        self.assertEqual(getattr(failed, "status_code", None), 409)
        self.assertEqual(payload["success"], False)
        self.assertEqual(payload["error"], "idempotency_key_failed")
        self.assertEqual(payload["idempotency_key"], "confirm:idem-1")
        self.assertEqual(payload["action_name"], "confirm_link")
        self.assertFalse(payload["retryable"])

    def test_reserved_expiration_helper_is_deterministic_for_fixed_now(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_idempotency")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")
        is_expired = getattr(module, "is_workbench_idempotency_reserved_expired")
        now = datetime(2026, 5, 31, 9, 0, tzinfo=timezone.utc)

        self.assertFalse(
            is_expired(
                record_class(
                    tenant_id="default",
                    actor_id="finance-1",
                    action_name="confirm_link",
                    idempotency_key="confirm:no-expiry",
                    request_fingerprint="fp",
                    status="reserved",
                    expires_at=None,
                ),
                now=now,
            )
        )
        self.assertFalse(
            is_expired(
                record_class(
                    tenant_id="default",
                    actor_id="finance-1",
                    action_name="confirm_link",
                    idempotency_key="confirm:future",
                    request_fingerprint="fp",
                    status="reserved",
                    expires_at=now + timedelta(seconds=1),
                ),
                now=now,
            )
        )
        self.assertTrue(
            is_expired(
                record_class(
                    tenant_id="default",
                    actor_id="finance-1",
                    action_name="confirm_link",
                    idempotency_key="confirm:past",
                    request_fingerprint="fp",
                    status="reserved",
                    expires_at=now,
                ),
                now=now,
            )
        )
        self.assertFalse(
            is_expired(
                record_class(
                    tenant_id="default",
                    actor_id="finance-1",
                    action_name="confirm_link",
                    idempotency_key="confirm:committed",
                    request_fingerprint="fp",
                    status="committed",
                    expires_at=now - timedelta(seconds=1),
                ),
                now=now,
            )
        )

    def test_in_memory_idempotency_repository_reserves_commits_and_detects_fingerprint_conflict(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        record_class = getattr(module, "WorkbenchIdempotencyRecord")
        repository_class = getattr(module, "InMemoryWorkbenchIdempotencyRepository")

        repository = repository_class()
        reserved = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp-1",
            request_payload={"case_id": "CASE-1", "cookie": "session=SECRET"},
        )

        self.assertEqual(reserved.status, "reserved")
        self.assertEqual(repository.get_committed_or_reserved(*reserved.unique_identity), reserved.record)

        committed = repository.commit(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-1",
            request_fingerprint="fp-1",
            response_payload={"case_id": "CASE-1"},
            source_versions={"2026-05": 9},
            outbox_event_ids=["event-9"],
        )

        self.assertIsInstance(committed, record_class)
        self.assertEqual(committed.status, "committed")
        self.assertEqual(committed.response_payload, {"case_id": "CASE-1"})
        self.assertTrue(repository.has_fingerprint_conflict(committed.unique_identity, "fp-2"))
        self.assertNotIn("SECRET", json.dumps(committed.to_storage_payload(), sort_keys=True))

    def test_in_memory_idempotency_repository_reports_existing_reserved_without_overwrite(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        repository_class = getattr(module, "InMemoryWorkbenchIdempotencyRepository")
        reservation_class = getattr(module, "WorkbenchIdempotencyReservation")

        repository = repository_class()
        first = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-reserved",
            request_fingerprint="fp-reserved-1",
            request_payload={"case_id": "CASE-1"},
        )
        second = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:idem-reserved",
            request_fingerprint="fp-reserved-1",
            request_payload={"case_id": "CASE-SHOULD-NOT-OVERWRITE"},
        )

        self.assertIsInstance(first, reservation_class)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.record.request_payload, {"case_id": "CASE-1"})
        self.assertEqual(
            repository.get_committed_or_reserved("default", "finance-1", "confirm:idem-reserved").request_payload,
            {"case_id": "CASE-1"},
        )

    def test_in_memory_idempotency_repository_takes_over_expired_same_fingerprint_reserved_record(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        repository_class = getattr(module, "InMemoryWorkbenchIdempotencyRepository")
        now = datetime.now(timezone.utc)
        repository = repository_class()

        first = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired",
            request_fingerprint="fp-expired",
            request_payload={"case_id": "CASE-OLD"},
            expires_at=now - timedelta(seconds=1),
        )
        second = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired",
            request_fingerprint="fp-expired",
            request_payload={"case_id": "CASE-RETRY"},
            expires_at=now + timedelta(minutes=5),
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertTrue(second.taken_over_expired)
        self.assertEqual(second.record.request_payload, {"case_id": "CASE-RETRY"})
        self.assertEqual(second.record.expires_at, now + timedelta(minutes=5))

    def test_in_memory_idempotency_repository_does_not_take_over_expired_different_fingerprint_record(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        repository_class = getattr(module, "InMemoryWorkbenchIdempotencyRepository")
        now = datetime.now(timezone.utc)
        repository = repository_class()
        repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired-conflict",
            request_fingerprint="fp-old",
            request_payload={"case_id": "CASE-OLD"},
            expires_at=now - timedelta(seconds=1),
        )

        second = repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:expired-conflict",
            request_fingerprint="fp-new",
            request_payload={"case_id": "CASE-NEW"},
            expires_at=now + timedelta(minutes=5),
        )

        self.assertFalse(second.created)
        self.assertFalse(second.taken_over_expired)
        self.assertEqual(second.record.request_fingerprint, "fp-old")
        self.assertEqual(second.record.request_payload, {"case_id": "CASE-OLD"})

    def test_in_memory_idempotency_repository_mark_failed_sanitizes_failed_payload(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        repository_class = getattr(module, "InMemoryWorkbenchIdempotencyRepository")
        repository = repository_class()
        repository.reserve(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:failed",
            request_fingerprint="fp-failed",
            request_payload={"case_id": "CASE-FAILED", "authorization": "Bearer SECRET"},
        )

        failed = repository.mark_failed(
            tenant_id="default",
            actor_id="finance-1",
            action_name="confirm_link",
            idempotency_key="confirm:failed",
            request_fingerprint="fp-failed",
            response_payload={"error": "boom", "token": "SECRET"},
        )

        self.assertEqual(failed.status, "failed")
        self.assertNotIn("SECRET", json.dumps(failed.to_storage_payload(), sort_keys=True))
        self.assertNotIn("authorization", failed.request_payload)
        self.assertNotIn("token", failed.response_payload)

    def test_uow_replays_committed_same_fingerprint_without_handler_or_outbox(self) -> None:
        stored_response = {
            "status": "committed",
            "request_fingerprint": "fp-confirm-1",
            "response_payload": {"case_id": "CASE-IDEM", "affected_row_ids": ["oa-1", "bank-1"]},
            "source_versions": {"2026-05": 11},
            "outbox_event_ids": ["event-11"],
        }
        idempotency = _OperationRecordingIdempotencyStore(committed={"confirm:idem-1": stored_response})
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(idempotency_store=idempotency, read_model_writer=writer)
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(
                action_name="confirm_link",
                scope_keys=["2026-05"],
                idempotency_key="confirm:idem-1",
                request_fingerprint="fp-confirm-1",
                payload={"case_id": "CASE-IDEM", "row_ids": ["oa-1", "bank-1"]},
            ),
            handler,
        )

        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual(result["case_id"], "CASE-IDEM")
        self.assertEqual(result["source_versions"], {"2026-05": 11})
        self.assertEqual(result["outbox_event_ids"], ["event-11"])

    def test_uow_rejects_same_key_with_different_fingerprint_without_handler_or_outbox(self) -> None:
        stored_response = {
            "status": "committed",
            "request_fingerprint": "fp-confirm-old",
            "response_payload": {"case_id": "CASE-IDEM"},
            "source_versions": {"2026-05": 10},
            "outbox_event_ids": ["event-10"],
        }
        idempotency = _OperationRecordingIdempotencyStore(committed={"confirm:idem-conflict": stored_response})
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(idempotency_store=idempotency, read_model_writer=writer)
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "idempotency|fingerprint|conflict"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:idem-conflict",
                    request_fingerprint="fp-confirm-new",
                    payload={"case_id": "CASE-IDEM", "row_ids": ["oa-2", "bank-2"]},
                ),
                handler,
            )

        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual([operation["op"] for operation in idempotency.operations], ["get"])

    def test_uow_rejects_existing_reserved_same_fingerprint_without_handler_or_outbox(self) -> None:
        stored_response = {
            "status": "reserved",
            "request_fingerprint": "fp-confirm-in-progress",
            "response_payload": {},
        }
        idempotency = _OperationRecordingIdempotencyStore(committed={"confirm:idem-progress": stored_response})
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(idempotency_store=idempotency, read_model_writer=writer)
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "in.progress|idempotency"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:idem-progress",
                    request_fingerprint="fp-confirm-in-progress",
                    payload={"case_id": "CASE-IDEM", "row_ids": ["oa-1", "bank-1"]},
                ),
                handler,
            )

        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual([operation["op"] for operation in idempotency.operations], ["get"])

    def test_uow_rejects_failed_same_fingerprint_without_handler_or_outbox(self) -> None:
        stored_response = {
            "status": "failed",
            "request_fingerprint": "fp-confirm-failed",
            "response_payload": {"error": "previous_failure"},
        }
        idempotency = _OperationRecordingIdempotencyStore(committed={"confirm:idem-failed": stored_response})
        writer = _RecordingDirtyOutboxWriter()
        connection = _RecordingConnection()
        uow = self._new_uow(
            connection=connection,
            idempotency_store=idempotency,
            read_model_writer=writer,
        )
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "failed|idempotency") as raised:
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:idem-failed",
                    request_fingerprint="fp-confirm-failed",
                    payload={"case_id": "CASE-IDEM", "row_ids": ["oa-1", "bank-1"]},
                ),
                handler,
            )

        payload = raised.exception.to_response_payload()
        self.assertEqual(payload["error"], "idempotency_key_failed")
        self.assertFalse(payload["retryable"])
        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual([operation["op"] for operation in idempotency.operations], ["get"])
        self.assertEqual(connection.opened, 0)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 0)

    def test_uow_rejects_failed_different_fingerprint_as_conflict_without_handler_or_outbox(self) -> None:
        stored_response = {
            "status": "failed",
            "request_fingerprint": "fp-confirm-old",
            "response_payload": {"error": "previous_failure"},
        }
        idempotency = _OperationRecordingIdempotencyStore(committed={"confirm:idem-failed-conflict": stored_response})
        writer = _RecordingDirtyOutboxWriter()
        connection = _RecordingConnection()
        uow = self._new_uow(
            connection=connection,
            idempotency_store=idempotency,
            read_model_writer=writer,
        )
        called = False

        def handler(ctx: object) -> dict[str, object]:
            nonlocal called
            called = True
            return {"case_id": "SHOULD-NOT-RUN", "affected_scope_keys": ["2026-05"]}

        with self.assertRaisesRegex(Exception, "idempotency|fingerprint|conflict"):
            self._run_uow(
                uow,
                _Command(
                    action_name="confirm_link",
                    scope_keys=["2026-05"],
                    idempotency_key="confirm:idem-failed-conflict",
                    request_fingerprint="fp-confirm-new",
                    payload={"case_id": "CASE-IDEM", "row_ids": ["oa-2", "bank-2"]},
                ),
                handler,
            )

        self.assertFalse(called)
        self.assertEqual(writer.calls, [])
        self.assertEqual([operation["op"] for operation in idempotency.operations], ["get"])
        self.assertEqual(connection.opened, 0)

    def test_uow_reserves_and_commits_idempotency_record_inside_same_transaction_after_outbox(self) -> None:
        connection = _RecordingConnection()
        idempotency = _OperationRecordingIdempotencyStore()
        writer = _RecordingDirtyOutboxWriter()
        uow = self._new_uow(connection=connection, idempotency_store=idempotency, read_model_writer=writer)

        def handler(ctx: object) -> dict[str, object]:
            ctx.pair_relations.record("save_relation", case_id="CASE-IDEM-NEW")
            ctx.pair_relations.record("append_history", case_id="CASE-IDEM-NEW")
            return {"case_id": "CASE-IDEM-NEW", "affected_scope_keys": ["2026-05"]}

        result = self._run_uow(
            uow,
            _Command(
                action_name="confirm_link",
                scope_keys=["2026-05"],
                idempotency_key="confirm:idem-new",
                request_fingerprint="fp-confirm-new",
                actor_id="finance-1",
                payload={"case_id": "CASE-IDEM-NEW", "row_ids": ["oa-1", "bank-1"]},
            ),
            handler,
        )

        self.assertEqual([operation["op"] for operation in idempotency.operations], ["get", "reserve", "commit"])
        self.assertEqual(idempotency.operations[-1]["key"], "confirm:idem-new")
        self.assertEqual(idempotency.operations[-1]["result"], result)
        self.assertEqual(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(connection.commits, 1)


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    key = f"{record_type}_rows"
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[key])
    return rows


def _json_response(response: object) -> dict[str, object]:
    return json.loads(response.body)


class WorkbenchIdempotencyApiCompatibilityTests(unittest.TestCase):
    READ_MODEL_VERSION = "idempotency-test-generation-1"

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        install_fresh_workbench_write_gate(app, version=self.READ_MODEL_VERSION)
        return app

    def _workbench_payload(self, app: Application, month: str = "2026-03") -> dict[str, object]:
        return build_grouped_workbench_projection(app, month)

    def _default_open_row_ids(self, app: Application) -> list[str]:
        payload = self._workbench_payload(app)
        return [
            str(_flatten_groups(payload["unpaired"]["groups"], "oa")[0]["id"]),
            str(_flatten_groups(payload["unpaired"]["groups"], "bank")[0]["id"]),
            str(_flatten_groups(payload["unpaired"]["groups"], "invoice")[0]["id"]),
        ]

    def _post(self, app: Application, path: str, payload: dict[str, object]) -> object:
        return app.handle_request("POST", path, json.dumps(payload))

    @contextmanager
    def _suppress_background_persistence(self, app: Application):
        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as read_model_persist,
        ):
            yield pair_relation_persist, read_model_persist

    def test_confirm_link_accepts_optional_idempotency_key_without_response_shape_change(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-IDEM-COMPAT",
                    "idempotency_key": "confirm:compat-1",
                    "request_idempotency_key": "confirm:compat-1",
                    "note": "idempotency compatibility covers documented mismatch path",
                    "expected_read_model_version": self.READ_MODEL_VERSION,
                },
            )

        self.assertEqual(response.status_code, 200, response.body)
        payload = _json_response(response)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "confirm_link")
        self.assertEqual(payload["case_id"], "CASE-IDEM-COMPAT")
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertEqual(pair_relation_persist.call_count, 1)
        self.assertEqual(read_model_persist.call_count, 1)


if __name__ == "__main__":
    unittest.main()
