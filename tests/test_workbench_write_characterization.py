from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_idempotency import InMemoryWorkbenchIdempotencyRepository
from fin_ops_platform.services.workbench_idempotency import workbench_request_fingerprint
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork
from tests.test_workbench_uow_contract import (
    _RecordingConnection,
    _RecordingDirtyOutboxWriter,
    _RecordingIdempotencyStore,
    _RecordingRepositoryFactory,
)


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    key = f"{record_type}_rows"
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[key])
    return rows


def _json_response(response) -> dict[str, object]:
    return json.loads(response.body)


_DOCUMENTED_MISMATCH_CONFIRM_NOTE = "characterization regression covers documented mismatch confirm path"


class _RelationCommandRepositoryFactory(_RecordingRepositoryFactory):
    def __init__(self, persisted: list[dict[str, object]]) -> None:
        super().__init__()
        self._persisted = persisted

    def __call__(self, transaction: object):
        repository = super().__call__(transaction)

        def save_workbench_pair_relations(
            snapshot: dict[str, object],
            *,
            changed_case_ids: list[str] | None = None,
        ) -> None:
            self._persisted.append(
                {
                    "transaction": transaction,
                    "changed_case_ids": list(changed_case_ids or []),
                    "snapshot": dict(snapshot),
                }
            )

        repository.pair_relations.save_workbench_pair_relations = save_workbench_pair_relations
        return repository


class WorkbenchWriteCharacterizationTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        return app

    def _workbench_payload(self, app: Application, month: str = "2026-03") -> dict[str, object]:
        response = app.handle_request("GET", f"/api/workbench?month={month}")
        self.assertEqual(response.status_code, 200, response.body)
        return _json_response(response)

    def _default_open_row_ids(self, app: Application) -> list[str]:
        payload = self._workbench_payload(app)
        return [
            _flatten_groups(payload["open"]["groups"], "oa")[0]["id"],
            _flatten_groups(payload["open"]["groups"], "bank")[0]["id"],
            _flatten_groups(payload["open"]["groups"], "invoice")[0]["id"],
        ]

    def _default_open_rows(self, app: Application) -> dict[str, dict[str, object]]:
        payload = self._workbench_payload(app)
        return {
            "oa": _flatten_groups(payload["open"]["groups"], "oa")[0],
            "bank": _flatten_groups(payload["open"]["groups"], "bank")[0],
            "invoice": _flatten_groups(payload["open"]["groups"], "invoice")[0],
        }

    def _default_invoice_row_id(self, app: Application) -> str:
        payload = self._workbench_payload(app)
        return str(_flatten_groups(payload["open"]["groups"], "invoice")[0]["id"])

    def _post(self, app: Application, path: str, payload: dict[str, object]):
        if path == "/api/workbench/actions/confirm-link":
            self._ensure_documented_mismatch_confirm_note(payload)
        return app.handle_request("POST", path, json.dumps(payload))

    def _ensure_documented_mismatch_confirm_note(self, payload: dict[str, object]) -> dict[str, object]:
        if not str(payload.get("note") or payload.get("comment") or "").strip():
            payload["note"] = _DOCUMENTED_MISMATCH_CONFIRM_NOTE
        return payload

    @contextmanager
    def _suppress_background_persistence(self, app: Application):
        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as read_model_persist,
        ):
            yield pair_relation_persist, read_model_persist

    def _install_confirm_link_uow(self, app: Application) -> tuple[_RecordingConnection, _RecordingDirtyOutboxWriter, list[dict[str, object]]]:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        persisted: list[dict[str, object]] = []
        app._workbench_confirm_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=_RelationCommandRepositoryFactory(persisted),
            read_model_refresh_writer=writer,
            idempotency_store=InMemoryWorkbenchIdempotencyRepository(),
        )
        return connection, writer, persisted

    def _install_cancel_link_uow(
        self,
        app: Application,
        *,
        fail_outbox: bool = False,
    ) -> tuple[_RecordingConnection, _RecordingDirtyOutboxWriter, list[dict[str, object]]]:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=fail_outbox)
        persisted: list[dict[str, object]] = []
        app._workbench_cancel_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=_RelationCommandRepositoryFactory(persisted),
            read_model_refresh_writer=writer,
            idempotency_store=InMemoryWorkbenchIdempotencyRepository(),
        )
        return connection, writer, persisted

    def _install_withdraw_link_uow(
        self,
        app: Application,
        *,
        fail_outbox: bool = False,
    ) -> tuple[_RecordingConnection, _RecordingDirtyOutboxWriter, list[dict[str, object]]]:
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter(fail=fail_outbox)
        persisted: list[dict[str, object]] = []
        app._workbench_withdraw_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=_RelationCommandRepositoryFactory(persisted),
            read_model_refresh_writer=writer,
            idempotency_store=InMemoryWorkbenchIdempotencyRepository(),
        )
        return connection, writer, persisted

    def _create_cash_special_relation(
        self,
        app: Application,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        special_metadata: dict[str, object] | None = None,
    ) -> None:
        app._workbench_pair_relation_service.replace_with_confirmed_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-03",
            special_metadata=special_metadata,
        )

    def _personal_advance_raw_payload(self) -> dict[str, object]:
        return {
            "month": "2026-03",
            "summary": {
                "oa_count": 1,
                "bank_count": 3,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 4,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-personal-advance-characterization-001",
                        "type": "oa",
                        "case_id": None,
                        "applicant": "测试员工",
                        "project_name": "个人暂借款",
                        "apply_type": "支付申请",
                        "amount": "300000.00",
                        "counterparty_name": "测试员工",
                        "reason": "个人暂借款",
                        "available_actions": ["detail", "confirm_link", "mark_exception"],
                    }
                ],
                "bank": [
                    {
                        "id": "bank-personal-advance-out-characterization-001",
                        "type": "bank",
                        "case_id": None,
                        "pay_receive_time": "2026-03-02 09:00:00",
                        "debit_amount": "300000.00",
                        "credit_amount": "",
                        "counterparty_name": "测试员工",
                        "available_actions": ["detail", "confirm_link", "mark_exception"],
                    },
                    {
                        "id": "bank-personal-advance-in-characterization-001",
                        "type": "bank",
                        "case_id": None,
                        "pay_receive_time": "2026-03-03 09:00:00",
                        "debit_amount": "",
                        "credit_amount": "200000.00",
                        "counterparty_name": "测试员工",
                        "available_actions": ["detail", "confirm_link", "mark_exception"],
                    },
                    {
                        "id": "bank-personal-advance-in-characterization-002",
                        "type": "bank",
                        "case_id": None,
                        "pay_receive_time": "2026-03-04 09:00:00",
                        "debit_amount": "",
                        "credit_amount": "100000.00",
                        "counterparty_name": "测试员工",
                        "available_actions": ["detail", "confirm_link", "mark_exception"],
                    },
                ],
                "invoice": [],
            },
        }

    def _personal_advance_row_ids(self) -> list[str]:
        return [
            "oa-personal-advance-characterization-001",
            "bank-personal-advance-out-characterization-001",
            "bank-personal-advance-in-characterization-001",
            "bank-personal-advance-in-characterization-002",
        ]

    def test_duplicate_confirm_link_with_same_case_id_replays_success_and_reschedules(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            first_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-DUP-SAME"},
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-DUP-SAME"},
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["case_id"], "CASE-DUP-SAME")
        self.assertEqual(second_payload["case_id"], "CASE-DUP-SAME")
        self.assertCountEqual(first_payload["affected_row_ids"], row_ids)
        self.assertCountEqual(second_payload["affected_row_ids"], row_ids)

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-DUP-SAME")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], row_ids)
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "confirm_link"],
        )
        self.assertEqual(pair_relation_persist.call_count, 2)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_confirm_link_uses_uow_transaction_when_available(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        persisted: list[dict[str, object]] = []
        repository_factory = _RelationCommandRepositoryFactory(persisted)
        app._workbench_confirm_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=repository_factory,
            read_model_refresh_writer=writer,
            idempotency_store=_RecordingIdempotencyStore(),
        )

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-UOW-CONFIRM",
                    "idempotency_key": "confirm:uow-confirm-1",
                },
            )

        self.assertEqual(response.status_code, 200, response.body)
        payload = _json_response(response)
        self.assertEqual(payload["case_id"], "CASE-UOW-CONFIRM")
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertTrue(payload["operation_projection"]["after"]["paired_groups"])
        self.assertEqual(pair_relation_persist.call_count, 0)
        self.assertEqual(read_model_persist.call_count, 0)
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(len(persisted), 1)
        self.assertIs(persisted[0]["transaction"], connection.transaction_obj)
        self.assertIn("CASE-UOW-CONFIRM", persisted[0]["changed_case_ids"])
        self.assertTrue(writer.calls)
        self.assertIs(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertEqual(repository_factory.created_for_transactions, [connection.transaction_obj])

    def test_confirm_link_uow_replays_same_idempotency_key_without_duplicate_outbox(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        connection, writer, persisted = self._install_confirm_link_uow(app)
        request_payload = {
            "month": "2026-03",
            "row_ids": row_ids,
            "case_id": "CASE-UOW-IDEMPOTENT",
            "idempotency_key": "confirm:uow-idem-replay",
        }

        first = self._post(app, "/api/workbench/actions/confirm-link", request_payload)
        first_outbox_count = len(writer.calls)
        second = self._post(app, "/api/workbench/actions/confirm-link", request_payload)

        self.assertEqual(first.status_code, 200, first.body)
        self.assertEqual(second.status_code, 200, second.body)
        self.assertEqual(_json_response(first), _json_response(second))
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(persisted), 1)
        self.assertGreater(first_outbox_count, 0)
        self.assertEqual(len(writer.calls), first_outbox_count)

    def test_confirm_link_uow_rejects_same_idempotency_key_with_different_payload(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        connection, writer, persisted = self._install_confirm_link_uow(app)

        first = self._post(
            app,
            "/api/workbench/actions/confirm-link",
            {
                "month": "2026-03",
                "row_ids": row_ids,
                "case_id": "CASE-UOW-IDEMPOTENT-CONFLICT",
                "idempotency_key": "confirm:uow-idem-conflict",
                "note": "first",
            },
        )
        first_outbox_count = len(writer.calls)
        second = self._post(
            app,
            "/api/workbench/actions/confirm-link",
            {
                "month": "2026-03",
                "row_ids": row_ids,
                "case_id": "CASE-UOW-IDEMPOTENT-CONFLICT",
                "idempotency_key": "confirm:uow-idem-conflict",
                "note": "changed",
            },
        )

        self.assertEqual(first.status_code, 200, first.body)
        self.assertEqual(second.status_code, 409, second.body)
        payload = _json_response(second)
        self.assertEqual(payload["error"], "idempotency_key_conflict")
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(persisted), 1)
        self.assertGreater(first_outbox_count, 0)
        self.assertEqual(len(writer.calls), first_outbox_count)

    def test_confirm_link_uow_returns_failed_idempotency_response_without_retry(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency_store = InMemoryWorkbenchIdempotencyRepository()
        app._workbench_confirm_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=_RecordingRepositoryFactory(),
            read_model_refresh_writer=writer,
            idempotency_store=idempotency_store,
        )
        request_payload = {
            "month": "2026-03",
            "row_ids": row_ids,
            "case_id": "CASE-UOW-FAILED",
            "idempotency_key": "confirm:uow-idem-failed",
        }
        self._ensure_documented_mismatch_confirm_note(request_payload)
        request_fingerprint = workbench_request_fingerprint(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="confirm_link",
            payload=request_payload,
        )
        idempotency_store.reserve(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="confirm_link",
            idempotency_key="confirm:uow-idem-failed",
            request_fingerprint=request_fingerprint,
            request_payload=request_payload,
        )
        idempotency_store.mark_failed(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="confirm_link",
            idempotency_key="confirm:uow-idem-failed",
            request_fingerprint=request_fingerprint,
            response_payload={"error": "previous_failure", "token": "SECRET"},
        )

        response = self._post(app, "/api/workbench/actions/confirm-link", request_payload)

        self.assertEqual(response.status_code, 409, response.body)
        payload = _json_response(response)
        self.assertEqual(payload["error"], "idempotency_key_failed")
        self.assertEqual(payload["idempotency_key"], "confirm:uow-idem-failed")
        self.assertFalse(payload["retryable"])
        self.assertEqual(connection.opened, 0)
        self.assertEqual(writer.calls, [])

    def test_duplicate_confirm_link_without_case_id_allocates_new_case_and_replaces_active_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            first_response = self._post(app, "/api/workbench/actions/confirm-link", {"month": "2026-03", "row_ids": row_ids})
            second_response = self._post(app, "/api/workbench/actions/confirm-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["case_id"], "CASE-AUTO-0001")
        self.assertEqual(second_payload["case_id"], "CASE-AUTO-0002")
        active_relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(active_relation)
        assert active_relation is not None
        self.assertEqual(active_relation["case_id"], "CASE-AUTO-0002")
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "confirm_link"],
        )

    def test_confirm_link_without_case_id_skips_existing_active_auto_relation_case_id(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-AUTO-0001",
            row_ids=["txn-existing-auto", "inv_existing_auto"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-03",
        )

        with self._suppress_background_persistence(app):
            response = self._post(app, "/api/workbench/actions/confirm-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(response.status_code, 200, response.body)
        payload = _json_response(response)
        self.assertEqual(payload["case_id"], "CASE-AUTO-0002")
        existing_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-AUTO-0001")
        self.assertIsNotNone(existing_relation)
        active_relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(active_relation)
        assert active_relation is not None
        self.assertEqual(active_relation["case_id"], "CASE-AUTO-0002")

    def test_duplicate_cancel_link_returns_not_found_after_first_cancel(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-DUP"},
            )
            first_cancel = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})
            second_cancel = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(first_cancel.status_code, 200, first_cancel.body)
        self.assertEqual(second_cancel.status_code, 404, second_cancel.body)
        self.assertEqual(_json_response(second_cancel)["error"], "workbench_pair_relation_not_found")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-DUP"))

    def test_cancel_link_uses_uow_transaction_when_available(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-UOW"},
            )
        connection, writer, persisted = self._install_cancel_link_uow(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            cancel_response = self._post(
                app,
                "/api/workbench/actions/cancel-link",
                {
                    "month": "2026-03",
                    "row_id": row_ids[1],
                    "idempotency_key": "cancel:uow-cancel-1",
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(cancel_response.status_code, 200, cancel_response.body)
        payload = _json_response(cancel_response)
        self.assertEqual(payload["case_id"], "CASE-CANCEL-UOW")
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertEqual(pair_relation_persist.call_count, 0)
        self.assertEqual(read_model_persist.call_count, 0)
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(len(persisted), 1)
        self.assertIs(persisted[0]["transaction"], connection.transaction_obj)
        self.assertEqual(persisted[0]["changed_case_ids"], ["CASE-CANCEL-UOW"])
        self.assertTrue(writer.calls)
        self.assertIs(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-UOW"))

    def test_cancel_link_uow_replays_same_idempotency_key_without_active_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-IDEMPOTENT"},
            )
        connection, writer, persisted = self._install_cancel_link_uow(app)
        request_payload = {
            "month": "2026-03",
            "row_id": row_ids[1],
            "idempotency_key": "cancel:uow-idem-replay",
        }

        first = self._post(app, "/api/workbench/actions/cancel-link", request_payload)
        first_outbox_count = len(writer.calls)
        second = self._post(app, "/api/workbench/actions/cancel-link", request_payload)

        self.assertEqual(first.status_code, 200, first.body)
        self.assertEqual(second.status_code, 200, second.body)
        self.assertEqual(_json_response(first), _json_response(second))
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(persisted), 1)
        self.assertGreater(first_outbox_count, 0)
        self.assertEqual(len(writer.calls), first_outbox_count)

    def test_cancel_link_uow_rejects_same_idempotency_key_with_different_payload_before_lookup(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-IDEMPOTENT-CONFLICT"},
            )
        connection, writer, persisted = self._install_cancel_link_uow(app)

        first = self._post(
            app,
            "/api/workbench/actions/cancel-link",
            {
                "month": "2026-03",
                "row_id": row_ids[1],
                "idempotency_key": "cancel:uow-idem-conflict",
                "comment": "first",
            },
        )
        first_outbox_count = len(writer.calls)
        second = self._post(
            app,
            "/api/workbench/actions/cancel-link",
            {
                "month": "2026-03",
                "row_id": row_ids[1],
                "idempotency_key": "cancel:uow-idem-conflict",
                "comment": "changed",
            },
        )

        self.assertEqual(first.status_code, 200, first.body)
        self.assertEqual(second.status_code, 409, second.body)
        self.assertEqual(_json_response(second)["error"], "idempotency_key_conflict")
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(len(persisted), 1)
        self.assertGreater(first_outbox_count, 0)
        self.assertEqual(len(writer.calls), first_outbox_count)

    def test_cancel_link_uow_returns_failed_idempotency_response_before_relation_lookup(self) -> None:
        app = self._build_app()
        connection = _RecordingConnection()
        writer = _RecordingDirtyOutboxWriter()
        idempotency_store = InMemoryWorkbenchIdempotencyRepository()
        app._workbench_cancel_link_uow_override = WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=_RecordingRepositoryFactory(),
            read_model_refresh_writer=writer,
            idempotency_store=idempotency_store,
        )
        request_payload = {
            "month": "2026-03",
            "row_id": "missing-row",
            "idempotency_key": "cancel:uow-idem-failed",
        }
        request_fingerprint = workbench_request_fingerprint(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="cancel_link",
            payload=request_payload,
        )
        idempotency_store.reserve(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="cancel_link",
            idempotency_key="cancel:uow-idem-failed",
            request_fingerprint=request_fingerprint,
            request_payload=request_payload,
        )
        idempotency_store.mark_failed(
            tenant_id="default",
            actor_id="test-user-id",
            action_name="cancel_link",
            idempotency_key="cancel:uow-idem-failed",
            request_fingerprint=request_fingerprint,
            response_payload={"error": "previous_failure"},
        )

        response = self._post(app, "/api/workbench/actions/cancel-link", request_payload)

        self.assertEqual(response.status_code, 409, response.body)
        payload = _json_response(response)
        self.assertEqual(payload["error"], "idempotency_key_failed")
        self.assertEqual(payload["idempotency_key"], "cancel:uow-idem-failed")
        self.assertFalse(payload["retryable"])
        self.assertEqual(connection.opened, 0)
        self.assertEqual(writer.calls, [])

    def test_cancel_link_uow_outbox_failure_restores_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-ROLLBACK"},
            )
        connection, writer, persisted = self._install_cancel_link_uow(app, fail_outbox=True)

        cancel_response = self._post(
            app,
            "/api/workbench/actions/cancel-link",
            {
                "month": "2026-03",
                "row_id": row_ids[1],
                "idempotency_key": "cancel:uow-rollback",
            },
        )

        self.assertEqual(cancel_response.status_code, 503, cancel_response.body)
        self.assertEqual(_json_response(cancel_response)["error"], "workbench_state_persistence_unavailable")
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(writer.calls, [])
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-ROLLBACK"))

    def test_cancel_link_uow_stale_expected_relation_does_not_open_transaction(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-STALE-OLD"},
            )
            self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-STALE-NEW"},
            )
        connection, writer, persisted = self._install_cancel_link_uow(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            cancel_response = self._post(
                app,
                "/api/workbench/actions/cancel-link",
                {
                    "month": "2026-03",
                    "row_id": row_ids[1],
                    "expected_versions": {"relation:CASE-CANCEL-STALE-OLD": 1},
                    "idempotency_key": "cancel:uow-stale",
                },
            )

        self.assertEqual(cancel_response.status_code, 409, cancel_response.body)
        self.assertEqual(connection.opened, 0)
        self.assertEqual(writer.calls, [])
        self.assertEqual(persisted, [])
        self.assertEqual(pair_relation_persist.call_count, 0)
        self.assertEqual(read_model_persist.call_count, 0)
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-STALE-NEW"))

    def test_duplicate_ignore_and_unignore_current_behavior(self) -> None:
        app = self._build_app()
        invoice_row_id = self._default_invoice_row_id(app)

        with self._suppress_background_persistence(app):
            first_ignore = self._post(
                app,
                "/api/workbench/actions/ignore-row",
                {"month": "2026-03", "row_id": invoice_row_id, "comment": "ignore once"},
            )
            second_ignore = self._post(
                app,
                "/api/workbench/actions/ignore-row",
                {"month": "2026-03", "row_id": invoice_row_id, "comment": "ignore twice"},
            )
            first_unignore = self._post(app, "/api/workbench/actions/unignore-row", {"month": "2026-03", "row_id": invoice_row_id})
            second_unignore = self._post(app, "/api/workbench/actions/unignore-row", {"month": "2026-03", "row_id": invoice_row_id})

        self.assertEqual(first_ignore.status_code, 200, first_ignore.body)
        self.assertEqual(second_ignore.status_code, 200, second_ignore.body)
        first_ignore_payload = _json_response(first_ignore)
        second_ignore_payload = _json_response(second_ignore)
        self.assertEqual(first_ignore_payload["exception_case_id"], second_ignore_payload["exception_case_id"])
        self.assertEqual(first_unignore.status_code, 200, first_unignore.body)
        self.assertEqual(second_unignore.status_code, 404, second_unignore.body)
        self.assertEqual(_json_response(second_unignore)["error"], "workbench_row_not_found")
        case = app._workbench_exception_case_service.snapshot()["cases"][first_ignore_payload["exception_case_id"]]
        self.assertEqual(case["status"], "cancelled")

    def test_duplicate_mark_exception_reuses_existing_case_and_replays_success(self) -> None:
        app = self._build_app()
        invoice_row_id = self._default_invoice_row_id(app)

        with self._suppress_background_persistence(app):
            first_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {
                    "month": "2026-03",
                    "row_id": invoice_row_id,
                    "exception_code": "pending_collection",
                    "comment": "pending once",
                },
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {
                    "month": "2026-03",
                    "row_id": invoice_row_id,
                    "exception_code": "pending_collection",
                    "comment": "pending twice",
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertEqual(first_payload["exception_case_id"], second_payload["exception_case_id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        case = app._workbench_exception_case_service.snapshot()["cases"][first_payload["exception_case_id"]]
        self.assertEqual(case["status"], "open")

    def test_duplicate_exception_apply_is_service_idempotent_at_http_boundary(self) -> None:
        app = self._build_app()
        rows = [
            {"id": "oa-exc-api-001", "type": "oa", "month": "2026-05", "apply_type": "付款申请", "amount": "100.00"},
            {
                "id": "bank-exc-api-001",
                "type": "bank",
                "month": "2026-05",
                "debit_amount": "100.00",
                "credit_amount": "",
                "summary": "支付供应商",
            },
            {
                "id": "invoice-exc-api-001",
                "type": "invoice",
                "month": "2026-05",
                "issue_date": "2026-05-10",
                "total_with_tax": "100.00",
                "invoice_type": "进项发票",
            },
        ]
        request_payload = {
            "month": "2026-05",
            "row_ids": ["oa-exc-api-001", "bank-exc-api-001", "invoice-exc-api-001"],
            "scenario_code": "expense_all_equal",
            "action_code": "confirm_closed",
            "payload": {},
        }

        with patch.object(app, "_resolve_live_rows_direct", return_value=rows), self._suppress_background_persistence(app):
            first_response = self._post(app, "/api/workbench/exception/apply", request_payload)
            second_response = self._post(app, "/api/workbench/exception/apply", request_payload)

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        first_payload = _json_response(first_response)
        second_payload = _json_response(second_response)
        self.assertFalse(first_payload["idempotent"])
        self.assertTrue(second_payload["idempotent"])
        self.assertEqual(first_payload["case"]["id"], second_payload["case"]["id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)

    def test_stale_confirm_after_ignore_creates_pair_relation_and_leaves_ignored_case_active(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            ignore_response = self._post(app, "/api/workbench/actions/ignore-row", {"month": "2026-03", "row_id": row_ids[2]})
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-CONFIRM"},
            )

        self.assertEqual(ignore_response.status_code, 200, ignore_response.body)
        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-CONFIRM")
        self.assertIsNotNone(relation)
        ignored_case_id = _json_response(ignore_response)["exception_case_id"]
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"][ignored_case_id]["status"], "ignored")

    def test_stale_ignore_after_confirm_keeps_active_relation_and_creates_ignored_case(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-IGNORE"},
            )
            ignore_response = self._post(app, "/api/workbench/actions/ignore-row", {"month": "2026-03", "row_id": row_ids[2]})

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(ignore_response.status_code, 200, ignore_response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-IGNORE")
        self.assertIsNotNone(relation)
        ignored_case_id = _json_response(ignore_response)["exception_case_id"]
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"][ignored_case_id]["status"], "ignored")

    def test_ignore_row_with_expected_open_rejects_confirmed_row(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        invoice_row_id = row_ids[2]

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-IGNORE-CONFIRMED"},
            )
            ignore_response = self._post(
                app,
                "/api/workbench/actions/ignore-row",
                {
                    "month": "2026-03",
                    "row_id": invoice_row_id,
                    "expected_versions": {f"row:{invoice_row_id}": "open"},
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(ignore_response.status_code, 409, ignore_response.body)
        ignore_payload = _json_response(ignore_response)
        self.assertEqual(ignore_payload["error"], "workbench_write_conflict")
        self.assertEqual(ignore_payload["conflict"]["action"], "ignore_row")
        self.assertIn(ignore_payload["conflict"]["reason"], {"stale_row_status", "stale_relation_identity"})
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-IGNORE-CONFIRMED"))
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})
        self.assertNotIn(invoice_row_id, app._workbench_override_service.snapshot()["row_overrides"])
        self.assertEqual(pair_relation_persist.call_count, 1)
        self.assertEqual(read_model_persist.call_count, 1)

    def test_stale_cancel_after_replaced_cancels_current_relation_by_row_id(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            old_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-OLD"},
            )
            replacement_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-NEW"},
            )
            cancel_response = self._post(app, "/api/workbench/actions/cancel-link", {"month": "2026-03", "row_id": row_ids[1]})

        self.assertEqual(old_response.status_code, 200, old_response.body)
        self.assertEqual(replacement_response.status_code, 200, replacement_response.body)
        self.assertEqual(cancel_response.status_code, 200, cancel_response.body)
        self.assertEqual(_json_response(cancel_response)["case_id"], "CASE-NEW")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-OLD"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-NEW"))

    def test_cancel_link_with_expected_relation_rejects_replaced_active_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            old_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-OLD"},
            )
            replacement_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CANCEL-NEW"},
            )
            cancel_response = self._post(
                app,
                "/api/workbench/actions/cancel-link",
                {
                    "month": "2026-03",
                    "row_id": row_ids[1],
                    "expected_versions": {"relation:CASE-CANCEL-OLD": 1},
                },
            )

        self.assertEqual(old_response.status_code, 200, old_response.body)
        self.assertEqual(replacement_response.status_code, 200, replacement_response.body)
        self.assertEqual(cancel_response.status_code, 409, cancel_response.body)
        cancel_payload = _json_response(cancel_response)
        self.assertEqual(cancel_payload["error"], "workbench_write_conflict")
        self.assertEqual(cancel_payload["conflict"]["action"], "cancel_link")
        self.assertIn(cancel_payload["conflict"]["reason"], {"stale_relation_identity", "stale_relation_version"})
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-OLD"))
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CANCEL-NEW"))
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "confirm_link"],
        )
        self.assertEqual(pair_relation_persist.call_count, 2)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_stale_exception_after_relation_returns_conflict_and_preserves_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-STALE-EXCEPTION"},
            )
            exception_response = self._post(
                app,
                "/api/workbench/actions/mark-exception",
                {"month": "2026-03", "row_id": row_ids[2], "exception_code": "pending_collection"},
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(exception_response.status_code, 409, exception_response.body)
        self.assertEqual(_json_response(exception_response)["error"], "active_pair_relation_conflict")
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-STALE-EXCEPTION"))
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})

    def test_read_model_scheduling_failure_propagates_after_pair_relation_fact_is_mutated(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock read model scheduling failure")),
        ):
            with self.assertRaisesRegex(RuntimeError, "mock read model scheduling failure"):
                self._post(
                    app,
                    "/api/workbench/actions/confirm-link",
                    {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-SCHEDULING-FAIL"},
                )

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-SCHEDULING-FAIL")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], row_ids)

    def test_duplicate_withdraw_link_after_display_only_history_returns_not_found_current_behavior(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-DUP"},
            )
            first_withdraw = self._post(app, "/api/workbench/actions/withdraw-link", {"month": "2026-03", "row_ids": row_ids})
            second_withdraw = self._post(app, "/api/workbench/actions/withdraw-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(first_withdraw.status_code, 200, first_withdraw.body)
        self.assertEqual(second_withdraw.status_code, 400, second_withdraw.body)
        first_payload = _json_response(first_withdraw)
        second_payload = _json_response(second_withdraw)
        self.assertCountEqual(first_payload["affected_row_ids"], row_ids)
        self.assertEqual(second_payload["error"], "workbench_relation_not_found")
        self.assertCountEqual(second_payload["row_ids"], row_ids)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-DUP"))
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            ["confirm_link", "withdraw_link"],
        )
        self.assertEqual(pair_relation_persist.call_count, 2)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_withdraw_link_invalidates_only_affected_scopes_without_global_all(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        lifecycle_calls: list[dict[str, object]] = []

        def record_lifecycle_event(event: str, **kwargs: object) -> dict[str, object]:
            lifecycle_calls.append({"event": event, **kwargs})
            return {}

        with (
            patch.object(app, "_execute_derived_data_lifecycle_event", side_effect=record_lifecycle_event),
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-SCOPE"},
            )
            lifecycle_calls.clear()
            withdraw_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link",
                {"month": "2026-03", "row_ids": row_ids},
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(withdraw_response.status_code, 200, withdraw_response.body)
        pair_relation_calls = [
            call
            for call in lifecycle_calls
            if call.get("event") == "pair_relation_changed"
        ]
        self.assertEqual(len(pair_relation_calls), 1)
        self.assertEqual(pair_relation_calls[0].get("include_all"), False)
        self.assertNotIn("all", pair_relation_calls[0].get("scope_keys") or [])
        metadata = pair_relation_calls[0].get("metadata")
        self.assertIsInstance(metadata, dict)
        assert isinstance(metadata, dict)
        self.assertIn("downstream_scope_types", metadata)
        self.assertIn("invoice_usage_scope_types", metadata)
        pending_invoice_scope_keys = metadata.get("pending_invoice_scope_keys")
        self.assertIsInstance(pending_invoice_scope_keys, list)
        assert isinstance(pending_invoice_scope_keys, list)
        self.assertTrue(any(str(scope_key).endswith(":2026-03") for scope_key in pending_invoice_scope_keys))
        self.assertNotIn("expense:all", pending_invoice_scope_keys)
        self.assertNotIn("income:all", pending_invoice_scope_keys)

    def test_confirm_link_invalidates_only_affected_scopes_without_global_all(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        lifecycle_calls: list[dict[str, object]] = []

        def record_lifecycle_event(event: str, **kwargs: object) -> dict[str, object]:
            lifecycle_calls.append({"event": event, **kwargs})
            return {}

        with (
            patch.object(app, "_execute_derived_data_lifecycle_event", side_effect=record_lifecycle_event),
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-CONFIRM-SCOPE"},
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        pair_relation_calls = [
            call
            for call in lifecycle_calls
            if call.get("event") == "pair_relation_changed"
        ]
        self.assertEqual(len(pair_relation_calls), 1)
        self.assertEqual(pair_relation_calls[0].get("include_all"), False)
        self.assertNotIn("all", pair_relation_calls[0].get("scope_keys") or [])
        metadata = pair_relation_calls[0].get("metadata")
        self.assertIsInstance(metadata, dict)
        assert isinstance(metadata, dict)
        self.assertEqual(metadata.get("source"), "confirm_link")
        self.assertEqual(metadata.get("action_name"), "confirm_link")
        pending_invoice_scope_keys = metadata.get("pending_invoice_scope_keys")
        if pending_invoice_scope_keys is not None:
            self.assertIsInstance(pending_invoice_scope_keys, list)
            assert isinstance(pending_invoice_scope_keys, list)
            self.assertTrue(any(str(scope_key).endswith(":2026-03") for scope_key in pending_invoice_scope_keys))
            self.assertNotIn("expense:all", pending_invoice_scope_keys)
            self.assertNotIn("income:all", pending_invoice_scope_keys)

    def test_withdraw_link_uses_uow_transaction_when_available(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)
        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-UOW"},
            )
        connection, writer, persisted = self._install_withdraw_link_uow(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            withdraw_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "idempotency_key": "withdraw:uow-withdraw-1",
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(withdraw_response.status_code, 200, withdraw_response.body)
        payload = _json_response(withdraw_response)
        self.assertEqual(payload["operation"], "withdraw_link")
        self.assertEqual(payload["affected_months"], ["2026-03"])
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertEqual(pair_relation_persist.call_count, 0)
        self.assertEqual(read_model_persist.call_count, 0)
        self.assertEqual(connection.opened, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(len(persisted), 1)
        self.assertIs(persisted[0]["transaction"], connection.transaction_obj)
        self.assertIn("CASE-WITHDRAW-UOW", persisted[0]["changed_case_ids"])
        self.assertTrue(writer.calls)
        self.assertIs(writer.calls[0]["transaction"], connection.transaction_obj)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-UOW"))

    def test_stale_withdraw_preview_withdraws_current_relation_without_restoring_same_row_set(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app):
            first_confirm = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-OLD"},
            )
            preview = self._post(app, "/api/workbench/actions/withdraw-link/preview", {"month": "2026-03", "row_ids": row_ids})
            replacement = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-NEW"},
            )
            stale_submit = self._post(app, "/api/workbench/actions/withdraw-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(first_confirm.status_code, 200, first_confirm.body)
        self.assertEqual(preview.status_code, 200, preview.body)
        self.assertEqual(replacement.status_code, 200, replacement.body)
        self.assertEqual(stale_submit.status_code, 200, stale_submit.body)
        # TODO(PF-P017+): stale submit acts on the current relation, not on the previewed relation version.
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-OLD"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-NEW"))
        restored_case_ids = [relation["case_id"] for relation in _json_response(stale_submit)["restored_relations"]]
        self.assertNotIn("CASE-WITHDRAW-OLD", restored_case_ids)

    def test_withdraw_submit_with_stale_preview_expected_versions_rejects_replacement_relation(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            first_confirm = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-EXPECTED-OLD"},
            )
            preview = self._post(app, "/api/workbench/actions/withdraw-link/preview", {"month": "2026-03", "row_ids": row_ids})
            replacement = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-EXPECTED-NEW"},
            )
            history_count = len(app._workbench_pair_relation_service.list_history())
            stale_submit = self._post(
                app,
                "/api/workbench/actions/withdraw-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "expected_versions": _json_response(preview)["submit_expected_versions"],
                },
            )

        self.assertEqual(first_confirm.status_code, 200, first_confirm.body)
        self.assertEqual(preview.status_code, 200, preview.body)
        self.assertEqual(replacement.status_code, 200, replacement.body)
        self.assertEqual(stale_submit.status_code, 409, stale_submit.body)
        payload = _json_response(stale_submit)
        self.assertEqual(payload["error"], "workbench_write_conflict")
        self.assertEqual(payload["conflict"]["action"], "withdraw_link")
        self.assertIn(payload["conflict"]["reason"], {"stale_relation_identity", "stale_relation_version"})
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-EXPECTED-OLD"))
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-EXPECTED-NEW"))
        self.assertEqual(len(app._workbench_pair_relation_service.list_history()), history_count)
        self.assertEqual(pair_relation_persist.call_count, 2)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_withdraw_link_read_model_scheduling_failure_rolls_back_relation_withdraw(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with patch.object(app, "_schedule_workbench_pair_relation_persist"):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-WITHDRAW-SCHEDULE-FAIL"},
            )
        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock withdraw read model failure")),
        ):
            response = self._post(app, "/api/workbench/actions/withdraw-link", {"month": "2026-03", "row_ids": row_ids})

        self.assertEqual(response.status_code, 503, response.body)
        self.assertEqual(_json_response(response)["error"], "workbench_state_persistence_unavailable")
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-WITHDRAW-SCHEDULE-FAIL"))
        self.assertNotEqual(app._workbench_pair_relation_service.list_history()[-1]["operation_type"], "withdraw_link")

    def test_duplicate_cash_special_updates_and_clears_are_replayed_current_behavior(self) -> None:
        app = self._build_app()
        pass_row_ids = ["oa-cash-pass-current", "bank-cash-pass-current"]
        ticket_row_ids = ["oa-cash-ticket-current", "bank-cash-ticket-current", "invoice-cash-ticket-current"]
        self._create_cash_special_relation(app, case_id="CASE-CASH-PASS-CURRENT", row_ids=pass_row_ids, row_types=["oa", "bank"])
        self._create_cash_special_relation(
            app,
            case_id="CASE-CASH-TICKET-CURRENT",
            row_ids=ticket_row_ids,
            row_types=["oa", "bank", "invoice"],
        )

        with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
            first_pass = self._post(
                app,
                "/api/workbench/actions/confirm-cash-pass-through",
                {"month": "2026-03", "row_ids": pass_row_ids, "cash_amount": "123.45", "note": "first pass"},
            )
            second_pass = self._post(
                app,
                "/api/workbench/actions/confirm-cash-pass-through",
                {"month": "2026-03", "row_ids": pass_row_ids, "cash_amount": "123.45", "note": "second pass"},
            )
            first_ticket = self._post(
                app,
                "/api/workbench/actions/confirm-cash-ticket-purchase",
                {
                    "month": "2026-03",
                    "row_ids": ticket_row_ids,
                    "cash_amount": "500.00",
                    "ticket_cost_amount": "300.00",
                    "project_name": "测试项目",
                    "note": "first ticket",
                },
            )
            second_ticket = self._post(
                app,
                "/api/workbench/actions/confirm-cash-ticket-purchase",
                {
                    "month": "2026-03",
                    "row_ids": ticket_row_ids,
                    "cash_amount": "500.00",
                    "ticket_cost_amount": "300.00",
                    "project_name": "测试项目",
                    "note": "second ticket",
                },
            )
            first_cancel = self._post(
                app,
                "/api/workbench/actions/cancel-cash-special",
                {"month": "2026-03", "row_ids": ticket_row_ids, "note": "first cancel"},
            )
            second_cancel = self._post(
                app,
                "/api/workbench/actions/cancel-cash-special",
                {"month": "2026-03", "row_ids": ticket_row_ids, "note": "second cancel"},
            )

        for response in (first_pass, second_pass, first_ticket, second_ticket, first_cancel, second_cancel):
            self.assertEqual(response.status_code, 200, response.body)
        pass_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CASH-PASS-CURRENT")
        ticket_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CASH-TICKET-CURRENT")
        assert pass_relation is not None
        assert ticket_relation is not None
        self.assertEqual(pass_relation["special_metadata"]["note"], "second pass")
        self.assertEqual(ticket_relation["special_metadata"], {})
        self.assertEqual(
            [entry["operation_type"] for entry in app._workbench_pair_relation_service.list_history()],
            [
                "confirm_link",
                "confirm_link",
                "update_special_relation",
                "update_special_relation",
                "update_special_relation",
                "update_special_relation",
                "clear_special_relation",
                "clear_special_relation",
            ],
        )
        self.assertEqual(pair_relation_persist.call_count, 6)
        self.assertEqual(read_model_persist.call_count, 6)

    def test_stale_cash_special_updates_first_active_relation_for_rows_current_behavior(self) -> None:
        app = self._build_app()
        row_ids = ["oa-cash-stale-current", "bank-cash-stale-current"]
        self._create_cash_special_relation(app, case_id="CASE-CASH-OLD-CURRENT", row_ids=row_ids, row_types=["oa", "bank"])
        self._create_cash_special_relation(app, case_id="CASE-CASH-NEW-CURRENT", row_ids=row_ids, row_types=["oa", "bank"])

        with self._suppress_background_persistence(app):
            response = self._post(
                app,
                "/api/workbench/actions/confirm-cash-pass-through",
                {"month": "2026-03", "row_ids": row_ids, "cash_amount": "1.00"},
            )

        self.assertEqual(response.status_code, 200, response.body)
        # TODO(PF-P017+): stale submit does not carry an expected relation version; it updates the current relation.
        old_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CASH-OLD-CURRENT")
        new_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CASH-NEW-CURRENT")
        self.assertIsNone(old_relation)
        assert new_relation is not None
        self.assertEqual(new_relation["special_metadata"]["special_type"], "cash_pass_through")

    def test_cash_special_with_stale_expected_relation_rejects_all_entrypoints(self) -> None:
        scenarios = [
            (
                "confirm_cash_pass_through",
                "/api/workbench/actions/confirm-cash-pass-through",
                ["oa-cash-stale-pass", "bank-cash-stale-pass"],
                ["oa", "bank"],
                {"cash_amount": "1.00"},
            ),
            (
                "confirm_cash_ticket_purchase",
                "/api/workbench/actions/confirm-cash-ticket-purchase",
                ["oa-cash-stale-ticket", "bank-cash-stale-ticket", "invoice-cash-stale-ticket"],
                ["oa", "bank", "invoice"],
                {"cash_amount": "500.00", "ticket_cost_amount": "300.00", "project_name": "测试项目"},
            ),
            (
                "cancel_cash_special",
                "/api/workbench/actions/cancel-cash-special",
                ["oa-cash-stale-cancel", "bank-cash-stale-cancel"],
                ["oa", "bank"],
                {},
            ),
        ]
        for action, path, row_ids, row_types, extra_payload in scenarios:
            with self.subTest(action=action):
                app = self._build_app()
                self._create_cash_special_relation(
                    app,
                    case_id=f"CASE-{action.upper()}-OLD",
                    row_ids=row_ids,
                    row_types=row_types,
                )
                existing_metadata = {"special_type": "existing", "note": "keep"}
                self._create_cash_special_relation(
                    app,
                    case_id=f"CASE-{action.upper()}-NEW",
                    row_ids=row_ids,
                    row_types=row_types,
                    special_metadata=existing_metadata,
                )
                history_count = len(app._workbench_pair_relation_service.list_history())

                with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
                    response = self._post(
                        app,
                        path,
                        {
                            "month": "2026-03",
                            "row_ids": row_ids,
                            "expected_versions": {f"relation:CASE-{action.upper()}-OLD": None},
                            **extra_payload,
                        },
                    )

                self.assertEqual(response.status_code, 409, response.body)
                payload = _json_response(response)
                self.assertEqual(payload["error"], "workbench_write_conflict")
                self.assertEqual(payload["conflict"]["action"], action)
                self.assertIn(payload["conflict"]["reason"], {"stale_relation_identity", "stale_relation_version"})
                old_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(f"CASE-{action.upper()}-OLD")
                new_relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(f"CASE-{action.upper()}-NEW")
                self.assertIsNone(old_relation)
                assert new_relation is not None
                self.assertEqual(new_relation["special_metadata"], existing_metadata)
                self.assertEqual(len(app._workbench_pair_relation_service.list_history()), history_count)
                self.assertEqual(pair_relation_persist.call_count, 0)
                self.assertEqual(read_model_persist.call_count, 0)

    def test_cash_special_scheduling_failure_propagates_after_metadata_mutation(self) -> None:
        app = self._build_app()
        row_ids = ["oa-cash-failure-current", "bank-cash-failure-current"]
        self._create_cash_special_relation(app, case_id="CASE-CASH-SCHEDULE-FAIL", row_ids=row_ids, row_types=["oa", "bank"])

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock cash read model failure")),
        ):
            with self.assertRaisesRegex(RuntimeError, "mock cash read model failure"):
                self._post(
                    app,
                    "/api/workbench/actions/confirm-cash-pass-through",
                    {"month": "2026-03", "row_ids": row_ids, "cash_amount": "10.00"},
                )

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-CASH-SCHEDULE-FAIL")
        assert relation is not None
        self.assertEqual(relation["special_metadata"]["special_type"], "cash_pass_through")

    def test_duplicate_update_bank_exception_reuses_case_and_reschedules_current_behavior(self) -> None:
        app = self._build_app()
        bank_row = self._default_open_rows(app)["bank"]

        with patch.object(app, "_schedule_workbench_read_model_persist") as read_model_persist:
            first_response = self._post(
                app,
                "/api/workbench/actions/update-bank-exception",
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "relation_code": "bank_fee",
                    "relation_label": "银行手续费",
                    "comment": "first fee",
                },
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/update-bank-exception",
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "relation_code": "bank_fee",
                    "relation_label": "银行手续费",
                    "comment": "second fee",
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        self.assertEqual(_json_response(first_response)["exception_case_id"], _json_response(second_response)["exception_case_id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_update_bank_exception_after_pair_relation_returns_conflict_current_behavior(self) -> None:
        app = self._build_app()
        rows = self._default_open_rows(app)
        oa_row = rows["oa"]
        bank_row = rows["bank"]

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": [oa_row["id"], bank_row["id"]], "case_id": "CASE-BANK-EXC-CONFLICT"},
            )
            exception_response = self._post(
                app,
                "/api/workbench/actions/update-bank-exception",
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "relation_code": "bank_fee",
                    "relation_label": "银行手续费",
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(exception_response.status_code, 409, exception_response.body)
        self.assertEqual(_json_response(exception_response)["error"], "active_pair_relation_conflict")
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BANK-EXC-CONFLICT"))
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})

    def test_update_bank_exception_scheduling_failure_propagates_after_case_and_override_are_persisted(self) -> None:
        app = self._build_app()
        bank_row = self._default_open_rows(app)["bank"]

        with patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock bank exception schedule failure")):
            with self.assertRaisesRegex(RuntimeError, "mock bank exception schedule failure"):
                self._post(
                    app,
                    "/api/workbench/actions/update-bank-exception",
                    {
                        "month": "2026-03",
                        "row_id": bank_row["id"],
                        "relation_code": "bank_fee",
                        "relation_label": "银行手续费",
                    },
                )

        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertIn(bank_row["id"], app._workbench_override_service.snapshot()["row_overrides"])

    def test_duplicate_oa_bank_exception_reuses_case_and_reschedules_current_behavior(self) -> None:
        app = self._build_app()
        rows = self._default_open_rows(app)
        row_ids = [rows["oa"]["id"], rows["bank"]["id"]]

        with patch.object(app, "_schedule_workbench_read_model_persist") as read_model_persist:
            first_response = self._post(
                app,
                "/api/workbench/actions/oa-bank-exception",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "first mismatch",
                },
            )
            second_response = self._post(
                app,
                "/api/workbench/actions/oa-bank-exception",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "second mismatch",
                },
            )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 200, second_response.body)
        self.assertEqual(_json_response(first_response)["exception_case_id"], _json_response(second_response)["exception_case_id"])
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertEqual(read_model_persist.call_count, 2)

    def test_oa_bank_exception_after_pair_relation_returns_conflict_and_preserves_relation(self) -> None:
        app = self._build_app()
        rows = self._default_open_rows(app)
        row_ids = [rows["oa"]["id"], rows["bank"]["id"]]

        with self._suppress_background_persistence(app):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-OA-BANK-CONFLICT"},
            )
            exception_response = self._post(
                app,
                "/api/workbench/actions/oa-bank-exception",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                },
            )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        self.assertEqual(exception_response.status_code, 409, exception_response.body)
        self.assertEqual(_json_response(exception_response)["error"], "active_pair_relation_conflict")
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-OA-BANK-CONFLICT"))
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})

    def test_oa_bank_exception_scheduling_failure_propagates_after_case_and_override_are_persisted(self) -> None:
        app = self._build_app()
        rows = self._default_open_rows(app)
        row_ids = [rows["oa"]["id"], rows["bank"]["id"]]

        with patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock oa bank schedule failure")):
            with self.assertRaisesRegex(RuntimeError, "mock oa bank schedule failure"):
                self._post(
                    app,
                    "/api/workbench/actions/oa-bank-exception",
                    {
                        "month": "2026-03",
                        "row_ids": row_ids,
                        "exception_code": "oa_bank_amount_mismatch",
                        "exception_label": "金额不一致，继续异常",
                    },
                )

        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertIn(rows["oa"]["id"], app._workbench_override_service.snapshot()["row_overrides"])
        self.assertIn(rows["bank"]["id"], app._workbench_override_service.snapshot()["row_overrides"])

    def test_duplicate_personal_advance_repayment_returns_not_found_after_first_settlement_current_behavior(self) -> None:
        app = self._build_app()
        row_ids = self._personal_advance_row_ids()

        with patch.object(app, "_build_raw_workbench_payload", return_value=self._personal_advance_raw_payload()):
            self._workbench_payload(app)
            with self._suppress_background_persistence(app) as (pair_relation_persist, read_model_persist):
                first_response = self._post(
                    app,
                    "/api/workbench/actions/confirm-personal-advance-repayment",
                    {"month": "2026-03", "row_ids": row_ids, "note": "first settlement"},
                )
                second_response = self._post(
                    app,
                    "/api/workbench/actions/confirm-personal-advance-repayment",
                    {"month": "2026-03", "row_ids": row_ids, "note": "second settlement"},
                )

        self.assertEqual(first_response.status_code, 200, first_response.body)
        self.assertEqual(second_response.status_code, 404, second_response.body)
        self.assertEqual(_json_response(second_response)["error"], "workbench_row_not_found")
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertEqual([relation["case_id"] for relation in app._workbench_pair_relation_service.list_active_relations()], ["CASE-WEX-000001"])
        self.assertEqual(pair_relation_persist.call_count, 1)
        self.assertEqual(read_model_persist.call_count, 1)

    def test_stale_personal_advance_after_exception_returns_not_found_and_preserves_exception(self) -> None:
        app = self._build_app()
        row_ids = self._personal_advance_row_ids()

        with patch.object(app, "_build_raw_workbench_payload", return_value=self._personal_advance_raw_payload()):
            self._workbench_payload(app)
            with patch.object(app, "_schedule_workbench_read_model_persist"):
                exception_response = self._post(
                    app,
                    "/api/workbench/actions/mark-exception",
                    {"month": "2026-03", "row_id": row_ids[0], "exception_code": "pending_collection"},
                )
            with self._suppress_background_persistence(app):
                repayment_response = self._post(
                    app,
                    "/api/workbench/actions/confirm-personal-advance-repayment",
                    {"month": "2026-03", "row_ids": row_ids},
                )

        self.assertEqual(exception_response.status_code, 200, exception_response.body)
        self.assertEqual(repayment_response.status_code, 404, repayment_response.body)
        self.assertEqual(_json_response(repayment_response)["error"], "workbench_row_not_found")
        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertEqual(app._workbench_pair_relation_service.snapshot()["pair_relations"], {})

    def test_personal_advance_persistence_failure_rolls_back_exception_case_and_relation(self) -> None:
        app = self._build_app()
        row_ids = self._personal_advance_row_ids()

        with patch.object(app, "_build_raw_workbench_payload", return_value=self._personal_advance_raw_payload()):
            self._workbench_payload(app)
            with patch.object(app, "_save_workbench_exception_cases_snapshot", side_effect=RuntimeError("mock settlement persist failure")):
                response = self._post(
                    app,
                    "/api/workbench/actions/confirm-personal-advance-repayment",
                    {"month": "2026-03", "row_ids": row_ids},
                )

        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(_json_response(response)["error"], "invalid_personal_advance_repayment_request")
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})
        self.assertEqual(app._workbench_pair_relation_service.snapshot()["pair_relations"], {})

    def test_personal_advance_scheduling_failure_propagates_after_case_and_relation_are_mutated(self) -> None:
        app = self._build_app()
        row_ids = self._personal_advance_row_ids()

        with patch.object(app, "_build_raw_workbench_payload", return_value=self._personal_advance_raw_payload()):
            self._workbench_payload(app)
            with (
                patch.object(app, "_schedule_workbench_pair_relation_persist"),
                patch.object(app, "_schedule_workbench_read_model_persist", side_effect=RuntimeError("mock repayment schedule failure")),
            ):
                with self.assertRaisesRegex(RuntimeError, "mock repayment schedule failure"):
                    self._post(
                        app,
                        "/api/workbench/actions/confirm-personal-advance-repayment",
                        {"month": "2026-03", "row_ids": row_ids},
                    )

        self.assertEqual(len(app._workbench_exception_case_service.snapshot()["cases"]), 1)
        self.assertEqual([relation["case_id"] for relation in app._workbench_pair_relation_service.list_active_relations()], ["CASE-WEX-000001"])


class WorkbenchWriteWorkerTriggerCharacterizationTests(unittest.TestCase):
    def test_http_process_dirty_worker_uses_opt_in_interval_and_starts_once(self) -> None:
        app = build_application()

        with patch("fin_ops_platform.app.server.Thread") as thread_class:
            self.assertFalse(app.start_workbench_matching_dirty_scope_worker(interval_seconds=0))
            self.assertFalse(thread_class.called)

            self.assertTrue(app.start_workbench_matching_dirty_scope_worker(interval_seconds=1))
            self.assertTrue(app.start_workbench_matching_dirty_scope_worker(interval_seconds=1))

        thread_class.assert_called_once()
        self.assertEqual(thread_class.call_args.kwargs["target"], app._run_workbench_matching_dirty_scope_worker)
        self.assertEqual(thread_class.call_args.kwargs["kwargs"], {"interval_seconds": 60.0})
        self.assertTrue(thread_class.call_args.kwargs["daemon"])
        thread_class.return_value.start.assert_called_once()

    def test_standalone_matching_loop_honors_max_iterations_without_sleeping_after_final_iteration(self) -> None:
        class FakeDirtyQueue:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def claim_due_scopes(self, **kwargs) -> list[str]:
                self.calls.append(dict(kwargs))
                return []

        dirty_queue = FakeDirtyQueue()
        sleep_calls: list[float] = []
        worker = WorkbenchMatchingDirtyScopeWorker(
            dirty_queue=dirty_queue,
            matching_orchestrator=object(),
            source_versions_provider=lambda: {},
            heartbeat_recorder=object(),
            config=WorkbenchMatchingDirtyScopeWorkerConfig(
                worker_id="worker-test",
                poll_interval_seconds=0,
                batch_size=3,
                lease_seconds=120,
                retry_delay_seconds=15,
                max_iterations=1,
                request_id_factory=lambda: "request-test",
            ),
            sleep=sleep_calls.append,
        )

        worker.run_forever()

        self.assertEqual(
            dirty_queue.calls,
            [
                {
                    "worker_id": "worker-test",
                    "limit": 3,
                    "lease_seconds": 120,
                    "request_id": "request-test",
                }
            ],
        )
        self.assertEqual(sleep_calls, [])


if __name__ == "__main__":
    unittest.main()
