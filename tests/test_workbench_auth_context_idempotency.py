from __future__ import annotations

import unittest
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_idempotency import WorkbenchIdempotencyInProgress
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_write_facade import (
    WorkbenchWriteFacade,
    WorkbenchWriteRelationReadSnapshotPort,
    WorkbenchWriteRelationSpecialMetadataMutationPort,
)


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
        if action_name == "withdraw_link":
            return {
                "success": True,
                "action": "withdraw_link",
                "operation": "withdraw_link",
                "month": getattr(command, "month"),
                "case_id": getattr(command, "case_id"),
                "affected_row_ids": list(getattr(command, "row_ids")),
                "affected_months": list(getattr(command, "scope_keys")),
                "affected_scope_keys": list(getattr(command, "scope_keys")),
                "restored_relations": [],
                "message": "已撤回 1 组关联。",
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


class _InProgressUoW:
    def replay_committed(self, command: object) -> None:
        raise WorkbenchIdempotencyInProgress(
            idempotency_key=str(getattr(command, "idempotency_key")),
            action_name=str(getattr(command, "action_name")),
        )

    def run(self, command: object, handler: object) -> dict[str, object]:
        raise WorkbenchIdempotencyInProgress(
            idempotency_key=str(getattr(command, "idempotency_key")),
            action_name=str(getattr(command, "action_name")),
        )


class _HandlerCallingUoW:
    def replay_committed(self, command: object) -> None:
        return None

    def run(self, command: object, handler: object) -> dict[str, object]:
        ctx = type("UoWContext", (), {"transaction": object(), "pair_relations": object()})()
        return handler(ctx)


class _PairRelationService:
    def __init__(self) -> None:
        self.replace_calls: list[object] = []
        self.cancel_calls: list[object] = []

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

    def replace_with_confirmed_relation(self, **kwargs: object) -> tuple[dict[str, object], dict[str, object]]:
        self.replace_calls.append(kwargs)
        raise AssertionError("WorkbenchWriteFacade must delegate confirm relation writes to WorkbenchRelationCommandService.")

    def cancel_relation_for_row_id(self, row_id: str) -> dict[str, object]:
        self.cancel_calls.append(row_id)
        raise AssertionError("WorkbenchWriteFacade must delegate cancel relation writes to WorkbenchRelationCommandService.")


class _RecordingRelationCommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []
        self.cancel_calls: list[dict[str, object]] = []
        self.preview_withdraw_calls: list[dict[str, object]] = []
        self.withdraw_calls: list[dict[str, object]] = []

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": str(kwargs["case_id"]),
            "row_ids": list(kwargs["row_ids"]),
            "row_types": list(kwargs["row_types"]),
            "status": "active",
            "relation_mode": str(kwargs["relation_mode"]),
            "month_scope": str(kwargs["month_scope"]),
            "amount_check": dict(kwargs.get("amount_check") or {}),
            "version": 1,
        }
        return {
            "status": "confirmed",
            "relation": relation,
            "changed_case_ids": [relation["case_id"]],
            "affected_months": ["2026-05"],
            "version": 1,
            "idempotent_replay": False,
        }

    def cancel_relation(self, **kwargs: object) -> dict[str, object]:
        self.cancel_calls.append(dict(kwargs))
        return {
            "status": "cancelled",
            "relation": {
                "case_id": str(kwargs["case_id"]),
                "row_ids": ["oa-1", "bank-1"],
                "status": "cancelled",
                "version": 4,
            },
            "changed_case_ids": [str(kwargs["case_id"])],
            "affected_months": ["2026-05"],
            "version": 4,
            "idempotent_replay": False,
        }

    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.preview_withdraw_calls.append(dict(kwargs))
        active_relation = {
            "case_id": "CASE-1",
            "row_ids": list(kwargs["row_ids"]),
            "row_types": ["oa", "bank"],
            "status": "active",
            "month_scope": "2026-05",
            "version": 3,
        }
        return {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": "withdraw_relation:CASE-1:3",
            "active_relation": {"case_id": "CASE-1", "version": 3},
            "before_relations": [active_relation],
            "after_relations": [],
            "submit_expected_versions": {"relation:CASE-1": 3},
        }

    def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.withdraw_calls.append(dict(kwargs))
        return {
            "status": "withdrawn",
            "relation": {
                "case_id": "CASE-1",
                "row_ids": ["oa-1", "bank-1"],
                "status": "cancelled",
                "version": 4,
            },
            "history": {"operation_type": "withdraw_link"},
            "changed_case_ids": ["CASE-1"],
            "affected_months": ["2026-05"],
            "affected_row_ids": ["oa-1", "bank-1"],
            "restored_relations": [],
            "version": 4,
            "idempotent_replay": False,
        }


class _NoActiveRelationCommandService:
    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        raise WorkbenchRelationCommandError(
            "workbench_relation_not_found",
            "Workbench relation is not active or does not exist.",
            payload={"row_ids": list(kwargs.get("row_ids") or [])},
        )


class _RecordingDecisionStore:
    def __init__(self, decisions: list[dict[str, object]]) -> None:
        self.decisions = [dict(decision) for decision in decisions]
        self.list_calls: list[dict[str, object]] = []
        self.suppress_calls: list[dict[str, object]] = []

    def list_decisions(self, scope_month: str, *, statuses: set[str] | None = None) -> list[dict[str, object]]:
        self.list_calls.append({"scope_month": scope_month, "statuses": set(statuses or set())})
        status_filter = set(statuses or set())
        return [
            dict(decision)
            for decision in self.decisions
            if decision.get("scope_month") == scope_month
            and (not status_filter or decision.get("decision_status") in status_filter)
        ]

    def suppress_by_row_ids(self, row_ids: list[str], *, exception_case_id: str) -> int:
        self.suppress_calls.append({"row_ids": list(row_ids), "exception_case_id": exception_case_id})
        requested = {str(row_id) for row_id in row_ids}
        changed = 0
        for decision in self.decisions:
            if decision.get("decision_status") not in {"paired", "open", "proposed"}:
                continue
            if requested.intersection(str(row_id) for row_id in list(decision.get("row_ids") or [])):
                decision["decision_status"] = "suppressed"
                decision["suppressed_by_exception_case_id"] = exception_case_id
                changed += 1
        return changed


class _ConflictingConfirmRelationCommandService:
    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        raise WorkbenchRelationCommandError(
            "workbench_relation_active_row_conflict",
            "One or more rows are already active in another workbench relation.",
            payload={
                "conflicting_case_ids": ["CASE-EXISTING"],
                "row_ids": list(kwargs.get("row_ids") or []),
            },
        )


class _BankInvoiceWithdrawRelationCommandService(_RecordingRelationCommandService):
    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.preview_withdraw_calls.append(dict(kwargs))
        active_relation = {
            "case_id": "CASE-BANK-INVOICE",
            "row_ids": ["bank-withdraw", "invoice-withdraw-a", "invoice-withdraw-b"],
            "row_types": ["bank", "invoice", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "version": 7,
        }
        return {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": "withdraw_relation:CASE-BANK-INVOICE:7",
            "active_relation": {"case_id": "CASE-BANK-INVOICE", "version": 7},
            "before_relations": [active_relation],
            "after_relations": [],
            "submit_expected_versions": {"relation:CASE-BANK-INVOICE": 7},
        }


class _RecordingExceptionCaseService:
    def __init__(self) -> None:
        self.created_cases: list[dict[str, object]] = []
        self._snapshot = {"cases": []}

    def snapshot(self) -> dict[str, object]:
        return dict(self._snapshot)

    def create_settlement_case(self, **kwargs: object) -> dict[str, object]:
        self.created_cases.append(dict(kwargs))
        return {"id": "ADV-1"}


def _personal_advance_rows() -> list[dict[str, object]]:
    return [
        {"id": "oa-advance-1", "type": "oa", "amount": "1000.00"},
        {"id": "bank-advance-out", "type": "bank", "debit_amount": "1000.00", "credit_amount": ""},
        {"id": "bank-advance-in", "type": "bank", "debit_amount": "", "credit_amount": "1000.00"},
    ]


def _new_facade(
    *,
    confirm_uow: object | None = None,
    cancel_uow: object | None = None,
    withdraw_uow: object | None = None,
    relation_command_service: object | None = None,
    exception_case_service: object | None = None,
    candidate_match_service: object | None = None,
    reconciliation_decision_store: object | None = None,
    candidate_persist_calls: list[dict[str, object]] | None = None,
    lifecycle_calls: list[dict[str, object]] | None = None,
    live_rows: list[dict[str, object]] | None = None,
    relation_groups: object | None = None,
    withdraw_rows_and_after_relations: object | None = None,
    scope_keys_for_row_ids: object | None = None,
    scope_keys_for_rows: object | None = None,
    resolve_rows_for_amount_check: object | None = None,
    resolved_row_types_for_row_ids: object | None = None,
) -> WorkbenchWriteFacade:
    pair_relation_service = _PairRelationService()
    return WorkbenchWriteFacade(
        relation_read_snapshot_port=WorkbenchWriteRelationReadSnapshotPort(pair_relation_service),
        relation_special_metadata_mutation_port=WorkbenchWriteRelationSpecialMetadataMutationPort(pair_relation_service),
        exception_service=object(),
        exception_case_service=exception_case_service or object(),
        override_service=object(),
        candidate_match_service=candidate_match_service or object(),
        next_case_id=lambda: "CASE-NEW",
        normalize_row_ids=lambda values: [str(value) for value in values],
        resolved_row_types_for_row_ids=resolved_row_types_for_row_ids or (
            lambda row_ids, **_: ["oa" if str(row_id).startswith("oa") else "bank" for row_id in row_ids]
        ),
        can_confirm_link_row_types=lambda **_: True,
        expand_confirm_link_row_ids_for_existing_context=lambda row_ids, **_: list(row_ids),
        amount_check_for_row_ids=lambda *_, **__: {},
        resolve_rows_for_amount_check=resolve_rows_for_amount_check or (lambda row_ids, **_: [{"id": row_id} for row_id in row_ids]),
        merge_relation_snapshots=lambda before, synthetic: list(before) + list(synthetic),
        synthetic_existing_case_relations=lambda *_, **__: [],
        month_scope_for_selected_row_ids=lambda **_: "2026-05",
        scope_keys_for_row_ids=scope_keys_for_row_ids or (lambda **_: {"2026-05"}),
        scope_keys_for_rows=scope_keys_for_rows or (lambda rows, **_: ["2026-05"]),
        resolve_live_rows_direct=lambda *_, **__: list(live_rows or []),
        resolve_live_row=lambda row_id, **_: {"id": row_id},
        relation_groups=relation_groups or (lambda *_, **__: []),
        withdraw_rows_and_after_relations=withdraw_rows_and_after_relations or (lambda *_, **__: ([], [], [])),
        amount_check_for_rows_by_type=lambda _: {},
        transaction_amount_for_row_id=lambda _: 0,
        build_workbench_payload=lambda *_, **__: {},
        build_ignored_rows_payload=lambda *_, **__: [],
        save_exception_cases_snapshot=lambda: None,
        persist_pair_relations=lambda **_: None,
        save_overrides_snapshot=lambda **_: None,
        persist_candidate_matches_best_effort=(
            lambda **kwargs: candidate_persist_calls.append(dict(kwargs))
            if candidate_persist_calls is not None
            else None
        ),
        restore_exception_write_snapshots=lambda **_: None,
        restore_exception_override_snapshots=lambda **_: None,
        restore_exception_pair_snapshots=lambda **_: None,
        schedule_pair_relation_persist=lambda **_: None,
        consume_reconciliation_decisions=lambda **_: 0,
        restore_pair_relation_snapshot=lambda *_, **__: None,
        execute_derived_data_lifecycle_event=(
            lambda *args, **kwargs: lifecycle_calls.append({"args": args, "kwargs": kwargs})
            if lifecycle_calls is not None
            else None
        ),
        emit_action_timing=lambda **_: None,
        confirm_link_uow=confirm_uow,
        cancel_link_uow=cancel_uow,
        withdraw_link_uow=withdraw_uow,
        persist_pair_relations_in_transaction=lambda **_: None,
        relation_command_service=relation_command_service,
        reconciliation_decision_store=reconciliation_decision_store,
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

    def test_confirm_link_response_returns_affected_scope_keys_only(self) -> None:
        facade = _new_facade(confirm_uow=_RecordingUoW())

        result = facade.confirm_link(
            {
                "month": "all",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:freshness-targets",
            },
            request_id="req-confirm-targets",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-05"])
        self.assertNotIn("read_model_scope_keys", result.payload)
        self.assertNotIn("freshness_targets", result.payload)
        self.assertNotIn("operation_barrier_targets", result.payload)

    def test_write_facade_does_not_read_legacy_read_model_scope_keys(self) -> None:
        source = Path("backend/src/fin_ops_platform/services/workbench_write_facade.py").read_text(encoding="utf-8")

        self.assertNotIn('get("read_model_scope_keys")', source)

    def test_confirm_link_two_pane_operation_projection_uses_open_groups(self) -> None:
        def relation_groups(relations: list[dict[str, object]], **_: object) -> list[dict[str, object]]:
            relation = relations[0]
            return [
                {
                    "group_id": f"case:{relation['case_id']}",
                    "group_type": relation["relation_mode"],
                    "oa_rows": [{"id": "oa-1", "type": "oa"}],
                    "bank_rows": [{"id": "bank-1", "type": "bank"}],
                    "invoice_rows": [],
                }
            ]

        facade = _new_facade(
            confirm_uow=_RecordingUoW(),
            relation_groups=relation_groups,
            resolve_rows_for_amount_check=lambda row_ids, **_: [
                {"id": "oa-1", "type": "oa"},
                {"id": "bank-1", "type": "bank"},
            ],
        )

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:two-pane-open-projection",
            },
            request_id="req-confirm-two-pane-open-projection",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        projection_after = result.payload["operation_projection"]["after"]
        self.assertEqual(projection_after["paired_groups"], [])
        self.assertEqual(projection_after["open_groups"][0]["group_id"], "case:CASE-NEW")

    def test_confirm_link_three_pane_operation_projection_uses_paired_groups(self) -> None:
        def relation_groups(relations: list[dict[str, object]], **_: object) -> list[dict[str, object]]:
            relation = relations[0]
            return [
                {
                    "group_id": f"case:{relation['case_id']}",
                    "group_type": relation["relation_mode"],
                    "oa_rows": [{"id": "oa-1", "type": "oa"}],
                    "bank_rows": [{"id": "bank-1", "type": "bank"}],
                    "invoice_rows": [{"id": "inv-1", "type": "invoice"}],
                }
            ]

        facade = _new_facade(
            confirm_uow=_RecordingUoW(),
            relation_groups=relation_groups,
            resolved_row_types_for_row_ids=lambda row_ids, **_: [
                "oa" if str(row_id).startswith("oa") else "invoice" if str(row_id).startswith("inv") else "bank"
                for row_id in row_ids
            ],
            resolve_rows_for_amount_check=lambda row_ids, **_: [
                {"id": "oa-1", "type": "oa"},
                {"id": "bank-1", "type": "bank"},
                {"id": "inv-1", "type": "invoice"},
            ],
        )

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1", "inv-1"],
                "idempotency_key": "confirm:three-pane-paired-projection",
            },
            request_id="req-confirm-three-pane-paired-projection",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        projection_after = result.payload["operation_projection"]["after"]
        self.assertEqual(projection_after["open_groups"], [])
        self.assertEqual(projection_after["paired_groups"][0]["group_id"], "case:CASE-NEW")

    def test_confirm_link_targets_resolved_row_months_when_row_ids_do_not_encode_month(self) -> None:
        uow = _RecordingUoW()
        row_ids = ["oa-imported-2048", "txn_imported_1361", "txn_imported_1269"]
        selected_rows = [
            {"id": "oa-imported-2048", "type": "oa", "summary_fields": {"申请日期": "2026-03-09"}},
            {"id": "txn_imported_1361", "type": "bank", "trade_time": "2026-03-09 12:06:30"},
            {"id": "txn_imported_1269", "type": "bank", "trade_time": "2026-02-03 09:16:49"},
        ]
        facade = _new_facade(
            confirm_uow=uow,
            resolve_rows_for_amount_check=lambda *_args, **_kwargs: selected_rows,
            scope_keys_for_row_ids=lambda **_: {"all"},
            scope_keys_for_rows=lambda rows, **_: [
                "all",
                *[
                    str(row.get("trade_time") or row.get("summary_fields", {}).get("申请日期"))[:7]
                    for row in rows
                    if str(row.get("trade_time") or row.get("summary_fields", {}).get("申请日期") or "")[:7]
                ],
            ],
        )

        result = facade.confirm_link(
            {
                "month": "all",
                "row_ids": row_ids,
                "idempotency_key": "confirm:resolved-row-months",
            },
            request_id="req-confirm-row-months",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(getattr(uow.run_commands[0], "scope_keys"), ["2026-03", "2026-02"])
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-03", "2026-02"])
        self.assertNotIn("read_model_scope_keys", result.payload)
        self.assertNotIn("freshness_targets", result.payload)
        self.assertNotIn("operation_barrier_targets", result.payload)

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

    def test_withdraw_link_replay_and_run_commands_use_explicit_actor_and_tenant_context(self) -> None:
        uow = _RecordingUoW()
        facade = _new_facade(
            withdraw_uow=uow,
            relation_command_service=_RecordingRelationCommandService(),
        )

        result = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "withdraw:actor-context",
            },
            request_id="req-withdraw",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(len(uow.replay_commands), 1)
        self.assertEqual(len(uow.run_commands), 1)
        for command in [*uow.replay_commands, *uow.run_commands]:
            self.assertEqual(getattr(command, "actor_id"), "oa-user-1")
            self.assertEqual(getattr(command, "tenant_id"), "default")

    def test_withdraw_link_response_returns_affected_scope_keys_only(self) -> None:
        facade = _new_facade(
            withdraw_uow=_RecordingUoW(),
            relation_command_service=_RecordingRelationCommandService(),
        )

        result = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "withdraw:freshness-targets",
            },
            request_id="req-withdraw-targets",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-05"])
        self.assertNotIn("read_model_scope_keys", result.payload)
        self.assertNotIn("freshness_targets", result.payload)
        self.assertNotIn("operation_barrier_targets", result.payload)

    def test_withdraw_link_targets_preview_row_months_when_relation_scope_is_all(self) -> None:
        class _AllScopePreviewRelationCommandService(_RecordingRelationCommandService):
            def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.preview_withdraw_calls.append(dict(kwargs))
                active_relation = {
                    "case_id": "CASE-ALL",
                    "row_ids": list(kwargs["row_ids"]),
                    "row_types": ["oa", "bank", "bank"],
                    "status": "active",
                    "month_scope": "all",
                    "version": 7,
                }
                return {
                    "operation": "withdraw_link",
                    "operation_type": "withdraw_relation",
                    "preview_id": "withdraw_relation:CASE-ALL:7",
                    "active_relation": active_relation,
                    "before_relations": [active_relation],
                    "after_relations": [],
                    "submit_expected_versions": {"relation:CASE-ALL": 7},
                }

        uow = _RecordingUoW()
        row_ids = ["oa-imported-2048", "txn_imported_1361", "txn_imported_1269"]
        preview_rows = [
            {"id": "oa-imported-2048", "type": "oa", "summary_fields": {"申请日期": "2026-03-09"}},
            {"id": "txn_imported_1361", "type": "bank", "trade_time": "2026-03-09 12:06:30"},
            {"id": "txn_imported_1269", "type": "bank", "trade_time": "2026-02-03 09:16:49"},
        ]
        facade = _new_facade(
            withdraw_uow=uow,
            relation_command_service=_AllScopePreviewRelationCommandService(),
            scope_keys_for_row_ids=lambda **_: {"all"},
            scope_keys_for_rows=lambda rows, **_: [
                "all",
                *[
                    str(row.get("trade_time") or row.get("summary_fields", {}).get("申请日期"))[:7]
                    for row in rows
                    if str(row.get("trade_time") or row.get("summary_fields", {}).get("申请日期") or "")[:7]
                ],
            ],
            withdraw_rows_and_after_relations=lambda **_: (preview_rows, [], row_ids),
        )

        result = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": row_ids,
                "idempotency_key": "withdraw:resolved-row-months",
            },
            request_id="req-withdraw-row-months",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(getattr(uow.run_commands[0], "scope_keys"), ["2026-03", "2026-02"])
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-03", "2026-02"])
        self.assertNotIn("read_model_scope_keys", result.payload)
        self.assertNotIn("freshness_targets", result.payload)
        self.assertNotIn("operation_barrier_targets", result.payload)

    def test_confirm_and_cancel_link_map_in_progress_idempotency_to_stable_conflict_payload(self) -> None:
        facade = _new_facade(confirm_uow=_InProgressUoW(), cancel_uow=_InProgressUoW())

        confirm = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:progress",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )
        cancel = facade.cancel_link(
            {
                "month": "2026-05",
                "row_id": "oa-1",
                "idempotency_key": "cancel:progress",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(confirm.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(confirm.payload["error"], "idempotency_key_in_progress")
        self.assertTrue(confirm.payload["retryable"])
        self.assertEqual(cancel.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(cancel.payload["error"], "idempotency_key_in_progress")
        self.assertTrue(cancel.payload["retryable"])

    def test_confirm_link_uow_preserves_relation_command_error(self) -> None:
        facade = _new_facade(
            confirm_uow=_HandlerCallingUoW(),
            relation_command_service=_ConflictingConfirmRelationCommandService(),
        )

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "case_id": "CASE-STALE",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["error"], "workbench_relation_active_row_conflict")
        self.assertEqual(result.payload["conflicting_case_ids"], ["CASE-EXISTING"])
        self.assertEqual(result.payload["row_ids"], ["oa-1", "bank-1"])

    def test_confirm_and_cancel_link_delegate_relation_writes_to_command_service_without_uow(self) -> None:
        relation_command = _RecordingRelationCommandService()
        facade = _new_facade(relation_command_service=relation_command)

        confirm = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "case_id": "CASE-REL-1",
                "note": "人工确认",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )
        cancel = facade.cancel_link(
            {
                "month": "2026-05",
                "row_id": "oa-1",
                "comment": "误关联",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(confirm.status_code, HTTPStatus.OK)
        self.assertEqual(cancel.status_code, HTTPStatus.OK)
        self.assertEqual(len(relation_command.confirm_calls), 1)
        self.assertEqual(relation_command.confirm_calls[0]["case_id"], "CASE-REL-1")
        self.assertEqual(relation_command.confirm_calls[0]["relation_mode"], "manual_confirmed")
        self.assertEqual(relation_command.confirm_calls[0]["actor_id"], "oa-user-1")
        self.assertEqual(relation_command.confirm_calls[0]["history_operation_type"], "confirm_link")
        self.assertIs(relation_command.confirm_calls[0]["replace_existing"], True)
        self.assertEqual(len(relation_command.cancel_calls), 1)
        self.assertEqual(relation_command.cancel_calls[0]["case_id"], "CASE-1")
        self.assertEqual(relation_command.cancel_calls[0]["actor_id"], "oa-user-1")
        self.assertEqual(relation_command.cancel_calls[0]["reason"], "误关联")

    def test_withdraw_link_preview_and_submit_delegate_to_relation_command_service(self) -> None:
        relation_command = _RecordingRelationCommandService()
        facade = _new_facade(relation_command_service=relation_command)

        preview = facade.preview_withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
            }
        )
        submit = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "operation_type": "withdraw_relation",
                "preview_id": preview.payload["preview_id"],
                "expected_versions": preview.payload["submit_expected_versions"],
                "idempotency_key": "withdraw:1",
            },
            request_id="req-withdraw-1",
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        self.assertEqual(submit.status_code, HTTPStatus.OK)
        self.assertEqual(len(relation_command.preview_withdraw_calls), 2)
        self.assertEqual(relation_command.preview_withdraw_calls[0]["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(relation_command.preview_withdraw_calls[0]["month_scope"], "2026-05")
        self.assertEqual(relation_command.preview_withdraw_calls[1]["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(relation_command.preview_withdraw_calls[1]["month_scope"], "2026-05")
        self.assertEqual(len(relation_command.withdraw_calls), 1)
        self.assertEqual(relation_command.withdraw_calls[0]["case_id"], "CASE-1")
        self.assertEqual(relation_command.withdraw_calls[0]["preview_id"], "withdraw_relation:CASE-1:3")
        self.assertEqual(relation_command.withdraw_calls[0]["operation_type"], "withdraw_relation")
        self.assertEqual(relation_command.withdraw_calls[0]["expected_versions"], {"relation:CASE-1": 3})
        self.assertEqual(relation_command.withdraw_calls[0]["idempotency_key"], "withdraw:1")

    def test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually(self) -> None:
        relation_command = _BankInvoiceWithdrawRelationCommandService()
        relation_group_app = object.__new__(Application)
        rows = [
            {
                "id": "bank-withdraw",
                "type": "bank",
                "case_id": "CASE-BANK-INVOICE",
                "amount": "10000.00",
                "counterparty": "中招国际招标有限公司云南分公司",
            },
            {
                "id": "invoice-withdraw-a",
                "type": "invoice",
                "case_id": "CASE-BANK-INVOICE",
                "amount": "9000.00",
                "buyer_name": "云南溯源科技有限公司",
            },
            {
                "id": "invoice-withdraw-b",
                "type": "invoice",
                "case_id": "CASE-BANK-INVOICE",
                "amount": "6716.32",
                "buyer_name": "云南溯源科技有限公司",
            },
        ]
        facade = _new_facade(
            relation_command_service=relation_command,
            relation_groups=relation_group_app._relation_groups,
            withdraw_rows_and_after_relations=lambda **_: (rows, [], [str(row["id"]) for row in rows]),
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["bank-withdraw", "invoice-withdraw-a", "invoice-withdraw-b"],
            }
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        after_groups = preview.payload["after"]["groups"]
        self.assertEqual(len(after_groups), 3)
        self.assertEqual(
            [
                (
                    len(group["bank_rows"]),
                    len(group["invoice_rows"]),
                    str(group["group_id"]),
                    str(group["reason"]),
                )
                for group in after_groups
            ],
            [
                (1, 0, "selected:bank-withdraw", "selected_row"),
                (0, 1, "selected:invoice-withdraw-a", "selected_row"),
                (0, 1, "selected:invoice-withdraw-b", "selected_row"),
            ],
        )
        for group in after_groups:
            self.assertEqual(group["oa_rows"], [])
            self.assertFalse(group["bank_rows"] and group["invoice_rows"])

    def test_withdraw_link_splits_pure_candidate_group_without_relation_history(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()
        candidate = candidate_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_bank_invoice",
                "status": "needs_review",
                "confidence": "medium",
                "rule_code": "same_counterparty_amount",
                "row_ids": ["oa-candidate", "bank-candidate", "invoice-candidate"],
                "oa_row_ids": ["oa-candidate"],
                "bank_row_ids": ["bank-candidate"],
                "invoice_row_ids": ["invoice-candidate"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "自动候选",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-06T10:00:00+00:00",
                "source_versions": {},
            }
        )
        persist_calls: list[dict[str, object]] = []
        facade = _new_facade(
            relation_command_service=_NoActiveRelationCommandService(),
            candidate_match_service=candidate_service,
            candidate_persist_calls=persist_calls,
            live_rows=[
                {"id": "oa-candidate", "type": "oa", "amount": "100.00"},
                {"id": "bank-candidate", "type": "bank", "amount": "100.00"},
                {"id": "invoice-candidate", "type": "invoice", "amount": "100.00"},
            ],
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-candidate"],
            }
        )
        submit = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-candidate"],
                "operation_type": "split_candidate",
                "preview_id": preview.payload["preview_id"],
                "expected_versions": preview.payload["submit_expected_versions"],
                "idempotency_key": "split-candidate:1",
            },
            request_id="req-split-candidate",
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        self.assertEqual(preview.payload["operation_type"], "split_candidate")
        self.assertEqual(preview.payload["candidate_keys"], [candidate["candidate_key"]])
        self.assertEqual(submit.status_code, HTTPStatus.OK)
        stored = candidate_service.list_candidates_by_month("2026-05")[0]
        self.assertEqual(stored["status"], "suppressed")
        self.assertEqual(stored["suppressed_reason"], "manual_override")
        self.assertEqual(persist_calls, [{"operation": "split_candidate"}])

    def test_withdraw_link_preview_splits_reconciliation_decision_when_no_active_relation(self) -> None:
        decision = {
            "decision_id": "decision-bank-invoice",
            "decision_key": "decision-bank-invoice",
            "scope_month": "2026-02",
            "display_state": "paired",
            "decision_status": "paired",
            "rule_code": "bank_invoice_exact_amount",
            "rule_version": "2026-06-15",
            "row_ids": ["bank-decision", "invoice-decision"],
            "bank_row_ids": ["bank-decision"],
            "invoice_row_ids": ["invoice-decision"],
        }
        decision_store = _RecordingDecisionStore([decision])
        facade = _new_facade(
            relation_command_service=_NoActiveRelationCommandService(),
            reconciliation_decision_store=decision_store,
            live_rows=[
                {
                    "id": "bank-decision",
                    "type": "bank",
                    "amount": "300.00",
                    "workbench_reconciliation_decision": dict(decision),
                },
                {
                    "id": "invoice-decision",
                    "type": "invoice",
                    "amount": "300.00",
                    "workbench_reconciliation_decision": dict(decision),
                },
            ],
            scope_keys_for_row_ids=lambda **_: {"all"},
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-decision", "invoice-decision"],
            }
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        self.assertEqual(preview.payload["operation_type"], "split_candidate")
        self.assertEqual(preview.payload["candidate_keys"], ["decision-bank-invoice"])
        self.assertEqual(preview.payload["affected_row_ids"], ["bank-decision", "invoice-decision"])
        self.assertIn("decision:decision-bank-invoice", preview.payload["submit_expected_versions"])
        self.assertIn("2026-02", [call["scope_month"] for call in decision_store.list_calls])

    def test_withdraw_link_submit_suppresses_reconciliation_decision_candidate(self) -> None:
        decision = {
            "decision_id": "decision-bank-invoice",
            "decision_key": "decision-bank-invoice",
            "scope_month": "2026-02",
            "display_state": "paired",
            "decision_status": "paired",
            "rule_code": "bank_invoice_exact_amount",
            "rule_version": "2026-06-15",
            "row_ids": ["bank-decision", "invoice-decision"],
            "bank_row_ids": ["bank-decision"],
            "invoice_row_ids": ["invoice-decision"],
        }
        decision_store = _RecordingDecisionStore([decision])
        lifecycle_calls: list[dict[str, object]] = []
        facade = _new_facade(
            relation_command_service=_NoActiveRelationCommandService(),
            reconciliation_decision_store=decision_store,
            lifecycle_calls=lifecycle_calls,
            live_rows=[
                {
                    "id": "bank-decision",
                    "type": "bank",
                    "amount": "300.00",
                    "workbench_reconciliation_decision": dict(decision),
                },
                {
                    "id": "invoice-decision",
                    "type": "invoice",
                    "amount": "300.00",
                    "workbench_reconciliation_decision": dict(decision),
                },
            ],
            scope_keys_for_row_ids=lambda **_: {"2026-02"},
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-decision", "invoice-decision"],
            }
        )
        submit = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-decision", "invoice-decision"],
                "operation_type": "split_candidate",
                "preview_id": preview.payload["preview_id"],
                "expected_versions": preview.payload["submit_expected_versions"],
                "idempotency_key": "split-decision:1",
            },
            request_id="req-split-decision",
        )

        self.assertEqual(submit.status_code, HTTPStatus.OK)
        self.assertEqual(submit.payload["operation"], "split_candidate")
        self.assertEqual(decision_store.decisions[0]["decision_status"], "suppressed")
        self.assertEqual(
            decision_store.suppress_calls,
            [
                {
                    "row_ids": ["bank-decision", "invoice-decision"],
                    "exception_case_id": "workbench_split_candidate",
                }
            ],
        )
        self.assertEqual(lifecycle_calls[0]["args"][0], "candidate_match_changed")
        self.assertEqual(lifecycle_calls[0]["kwargs"]["scope_keys"], ["2026-02"])

    def test_confirm_and_cancel_link_fail_fast_without_relation_command_service(self) -> None:
        facade = _new_facade()

        confirm = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "case_id": "CASE-REL-MISSING-COMMAND",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )
        cancel = facade.cancel_link(
            {
                "month": "2026-05",
                "row_id": "oa-1",
            },
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(confirm.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(confirm.payload["error"], "workbench_relation_command_unavailable")
        self.assertEqual(cancel.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(cancel.payload["error"], "workbench_relation_command_unavailable")

    def test_personal_advance_repayment_delegates_relation_write_to_command_service(self) -> None:
        relation_command = _RecordingRelationCommandService()
        exception_cases = _RecordingExceptionCaseService()
        rows = _personal_advance_rows()
        facade = _new_facade(
            relation_command_service=relation_command,
            exception_case_service=exception_cases,
            live_rows=rows,
        )

        result = facade.confirm_personal_advance_repayment(
            {
                "month": "2026-05",
                "row_ids": [str(row["id"]) for row in rows],
                "note": "个人暂借款还清",
            },
            request_id="req-personal-advance",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(len(exception_cases.created_cases), 1)
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertEqual(call["case_id"], "CASE-ADV-1")
        self.assertEqual(call["row_ids"], ["oa-advance-1", "bank-advance-out", "bank-advance-in"])
        self.assertEqual(call["row_types"], ["oa", "bank", "bank"])
        self.assertEqual(call["relation_mode"], "personal_advance_repayment_settlement")
        self.assertEqual(call["history_operation_type"], "confirm_personal_advance_repayment")
        self.assertIs(call["replace_existing"], True)
        self.assertEqual(call["special_metadata"]["cost_policy"], "exclude_all")
        self.assertEqual(call["amount_check"]["status"], "matched")
        self.assertEqual(result.payload["case_id"], "CASE-ADV-1")

    def test_personal_advance_repayment_fails_fast_without_relation_command_service(self) -> None:
        exception_cases = _RecordingExceptionCaseService()
        rows = _personal_advance_rows()
        facade = _new_facade(
            exception_case_service=exception_cases,
            live_rows=rows,
        )

        result = facade.confirm_personal_advance_repayment(
            {
                "month": "2026-05",
                "row_ids": [str(row["id"]) for row in rows],
            },
            request_id="req-personal-advance-missing-command",
        )

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "workbench_relation_command_unavailable")
        self.assertEqual(exception_cases.created_cases, [])

    def test_workbench_handlers_pass_request_local_oa_session_actor_to_live_write_path(self) -> None:
        session = _session()
        captured: dict[str, object] = {}
        app = object.__new__(Application)
        app._oa_identity_service = object()
        app._access_control_service = object()
        app._load_json_body = lambda body: ({"month": "2026-05"}, None)
        app._workbench_write_sync_guard = lambda: None

        def live_confirm(payload: dict[str, object], *, request_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None) -> Response:
            captured["confirm"] = {"actor_id": actor_id, "tenant_id": tenant_id, "request_id": request_id}
            return Response(status_code=200, body="{}")

        def live_cancel(payload: dict[str, object], *, request_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None) -> Response:
            captured["cancel"] = {"actor_id": actor_id, "tenant_id": tenant_id, "request_id": request_id}
            return Response(status_code=200, body="{}")

        class WithdrawFacade:
            def withdraw_link(self, payload: dict[str, object], *, request_id: str | None = None, actor_id: str | None = None, tenant_id: str | None = None) -> object:
                captured["withdraw"] = {"actor_id": actor_id, "tenant_id": tenant_id, "request_id": request_id}
                return object()

        app._handle_live_workbench_confirm_link = live_confirm
        app._handle_live_workbench_cancel_link = live_cancel
        app._workbench_write_facade = lambda: WithdrawFacade()
        app._workbench_write_response = lambda result: Response(status_code=200, body="{}")

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
            withdraw_response = Application._handle_api_workbench_withdraw_link(
                app,
                "{}",
                request_id="req-withdraw",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertEqual(captured["confirm"], {"actor_id": "oa-user-1", "tenant_id": "default", "request_id": "req-confirm"})
        self.assertEqual(captured["cancel"], {"actor_id": "oa-user-1", "tenant_id": "default", "request_id": "req-cancel"})
        self.assertEqual(captured["withdraw"], {"actor_id": "oa-user-1", "tenant_id": "default", "request_id": "req-withdraw"})


if __name__ == "__main__":
    unittest.main()
