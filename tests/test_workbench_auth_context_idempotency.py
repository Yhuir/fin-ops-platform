from __future__ import annotations

import unittest
from http import HTTPStatus
from unittest.mock import patch

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.workbench_write_facade import WorkbenchWriteFacade


class _RecordingUoW:
    def __init__(self) -> None:
        self.replay_commands: list[object] = []
        self.run_commands: list[object] = []

    def replay_committed(self, command: object) -> None:
        self.replay_commands.append(command)
        return None

    def run(self, command: object, handler: object) -> dict[str, object]:
        self.run_commands.append(command)
        action_name = str(getattr(command, "action_name", ""))
        if action_name == "cancel_link":
            return {
                "success": True,
                "action": "cancel_link",
                "month": getattr(command, "month"),
                "case_id": getattr(command, "case_id"),
                "affected_row_ids": list(getattr(command, "affected_row_ids")),
                "affected_months": list(getattr(command, "scope_keys")),
                "affected_scope_keys": list(getattr(command, "scope_keys")),
                "message": "已取消关联并回退为待处理。",
            }
        return {
            "success": True,
            "action": "confirm_link",
            "month": getattr(command, "month"),
            "case_id": getattr(command, "case_id"),
            "affected_row_ids": list(getattr(command, "row_ids")),
            "affected_months": list(getattr(command, "scope_keys")),
            "affected_scope_keys": list(getattr(command, "scope_keys")),
            "amount_check": {},
            "message": "已确认 2 条记录关联。",
        }


class _PairRelationService:
    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        return []

    def snapshot(self) -> dict[str, object]:
        return {}

    def get_active_relation_by_row_id(self, row_id: str) -> dict[str, object]:
        return {
            "case_id": "CASE-1",
            "row_ids": [row_id, "bank-1"],
            "month_scope": "2026-05",
            "version": 3,
        }


def _new_facade(*, confirm_uow: object | None = None, cancel_uow: object | None = None) -> WorkbenchWriteFacade:
    pair_relation_service = _PairRelationService()
    return WorkbenchWriteFacade(
        pair_relation_service=pair_relation_service,
        exception_service=object(),
        exception_case_service=object(),
        override_service=object(),
        candidate_match_service=object(),
        next_case_id=lambda: "CASE-NEW",
        normalize_row_ids=lambda values: [str(value) for value in values],
        resolved_row_types_for_row_ids=lambda row_ids, **_: ["oa" if str(row_id).startswith("oa") else "bank" for row_id in row_ids],
        can_confirm_link_row_types=lambda **_: True,
        expand_confirm_link_row_ids_for_existing_context=lambda row_ids, **_: list(row_ids),
        amount_check_for_row_ids=lambda *_, **__: {},
        resolve_rows_for_amount_check=lambda row_ids, **_: [{"id": row_id} for row_id in row_ids],
        merge_relation_snapshots=lambda before, synthetic: list(before) + list(synthetic),
        synthetic_existing_case_relations=lambda *_, **__: [],
        month_scope_for_selected_row_ids=lambda **_: "2026-05",
        scope_keys_for_row_ids=lambda **_: {"2026-05"},
        scope_keys_for_rows=lambda rows, **_: ["2026-05"],
        resolve_live_rows_direct=lambda *_, **__: [],
        resolve_live_row=lambda row_id, **_: {"id": row_id},
        relation_groups=lambda *_, **__: [],
        withdraw_rows_and_after_relations=lambda *_, **__: ([], [], []),
        amount_check_for_rows_by_type=lambda _: {},
        transaction_amount_for_row_id=lambda _: 0,
        build_workbench_payload=lambda *_, **__: {},
        build_ignored_rows_payload=lambda *_, **__: [],
        save_exception_cases_snapshot=lambda: None,
        persist_pair_relations=lambda **_: None,
        save_overrides_snapshot=lambda **_: None,
        persist_candidate_matches_best_effort=lambda **_: None,
        restore_exception_write_snapshots=lambda **_: None,
        restore_exception_override_snapshots=lambda **_: None,
        restore_exception_pair_snapshots=lambda **_: None,
        schedule_pair_relation_persist=lambda **_: None,
        consume_reconciliation_decisions=lambda **_: 0,
        restore_pair_relation_snapshot=lambda *_, **__: None,
        execute_derived_data_lifecycle_event=lambda *_, **__: None,
        schedule_read_model_persist=lambda *_, **__: None,
        emit_action_timing=lambda **_: None,
        confirm_link_uow=confirm_uow,
        cancel_link_uow=cancel_uow,
        persist_pair_relations_in_transaction=lambda **_: None,
    )


def _session() -> OARequestSession:
    return OARequestSession(
        token="token",
        identity=OAUserIdentity(
            user_id="oa-user-1",
            username="finance.owner",
            nickname="财务",
            display_name="财务负责人",
            roles=["finance"],
            permissions=["finops:app:view"],
        ),
        allowed=True,
        access_tier="full_access",
        can_access_app=True,
        can_mutate_data=True,
        can_admin_access=False,
    )


class WorkbenchAuthContextIdempotencyTests(unittest.TestCase):
    def test_confirm_link_command_uses_explicit_actor_and_tenant_context(self) -> None:
        uow = _RecordingUoW()
        facade = _new_facade(confirm_uow=uow)

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:1",
            },
            request_id="req-1",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(len(uow.run_commands), 1)
        command = uow.run_commands[0]
        self.assertEqual(getattr(command, "actor_id"), "oa-user-1")
        self.assertEqual(getattr(command, "tenant_id"), "default")

    def test_cancel_link_replay_and_run_commands_use_explicit_actor_and_tenant_context(self) -> None:
        uow = _RecordingUoW()
        facade = _new_facade(cancel_uow=uow)

        result = facade.cancel_link(
            {
                "month": "2026-05",
                "row_id": "oa-1",
                "idempotency_key": "cancel:1",
            },
            request_id="req-2",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(len(uow.replay_commands), 1)
        self.assertEqual(len(uow.run_commands), 1)
        for command in [*uow.replay_commands, *uow.run_commands]:
            self.assertEqual(getattr(command, "actor_id"), "oa-user-1")
            self.assertEqual(getattr(command, "tenant_id"), "default")

    def test_workbench_handlers_pass_request_local_oa_session_actor_to_live_write_path(self) -> None:
        session = _session()
        captured: dict[str, object] = {}
        app = object.__new__(Application)
        app._oa_identity_service = object()
        app._access_control_service = object()
        app._load_json_body = lambda body: ({"month": "2026-05"}, None)
        app._workbench_write_freshness_guard = lambda: None

        def live_confirm(payload: dict[str, object], *, request_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None) -> Response:
            captured["confirm"] = {"actor_id": actor_id, "tenant_id": tenant_id, "request_id": request_id}
            return Response(status_code=200, body="{}")

        def live_cancel(payload: dict[str, object], *, request_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None) -> Response:
            captured["cancel"] = {"actor_id": actor_id, "tenant_id": tenant_id, "request_id": request_id}
            return Response(status_code=200, body="{}")

        app._handle_live_workbench_confirm_link = live_confirm
        app._handle_live_workbench_cancel_link = live_cancel

        with patch("fin_ops_platform.app.server.resolve_oa_request_session", return_value=session):
            confirm_response = Application._handle_api_workbench_confirm_link(
                app,
                "{}",
                request_id="req-confirm",
                headers={"Authorization": "Bearer token"},
            )
            cancel_response = Application._handle_api_workbench_cancel_link(
                app,
                "{}",
                request_id="req-cancel",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(captured["confirm"], {"actor_id": "oa-user-1", "tenant_id": "default", "request_id": "req-confirm"})
        self.assertEqual(captured["cancel"], {"actor_id": "oa-user-1", "tenant_id": "default", "request_id": "req-cancel"})


if __name__ == "__main__":
    unittest.main()
