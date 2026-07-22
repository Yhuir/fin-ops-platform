from __future__ import annotations

import unittest
from copy import deepcopy
from http import HTTPStatus
from unittest.mock import patch

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.workbench_idempotency import WorkbenchIdempotencyInProgress
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_grouping import (
    WorkbenchRelationPreviewGroupingService,
)
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
            ctx = type("UoWContext", (), {"transaction": object(), "pair_relations": object()})()
            return handler(ctx)
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


def _preview_relation_groups():
    return WorkbenchRelationPreviewGroupingService(
        serialize_value=deepcopy,
        row_type_for_row_id=lambda row_id: str(row_id).split("-", 1)[0],
        derive_row_tags=lambda row, group, relation: [],
    ).group_relations


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


class _SnapshotForbiddenPairRelationService(_PairRelationService):
    def snapshot(self) -> dict[str, object]:
        raise AssertionError("UoW withdraw path must not read or restore the legacy pair relation snapshot.")


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
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-05"],
            "refresh_enqueued": False,
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
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-05"],
            "refresh_enqueued": False,
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
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-05"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }


class _NoActiveRelationCommandService:
    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        raise WorkbenchRelationCommandError(
            "workbench_relation_not_found",
            "Workbench relation is not active or does not exist.",
            payload={"row_ids": list(kwargs.get("row_ids") or [])},
        )


class _StaleConfirmRelationCommandService:
    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        raise WorkbenchRelationCommandError(
            "workbench_relation_read_model_not_fresh",
            "Workbench relation read model is refreshing.",
            payload={
                "read_model_status": "refreshing",
                "read_model_stale_reasons": ["dirty_scope_pending"],
                "read_model_scope_keys": ["2026-05"],
                "refresh_enqueued": True,
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


class _RawOaAliasWithdrawRelationCommandService(_RecordingRelationCommandService):
    raw_oa_row_id = "oa-exp-69fab21659b12d7d42a50a45"
    canonical_oa_row_id = "oa-exp-2156"
    bank_row_id = "txn_imported_0405"
    invoice_row_id = "oa-att-inv-oa-exp-69fab21659b12d7d42a50a45:item:0:fb2a9c9fab23-b515bf77d490fdfe"

    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.preview_withdraw_calls.append(dict(kwargs))
        active_relation = {
            "case_id": "CASE-RAW-OA",
            "row_ids": [self.raw_oa_row_id, self.bank_row_id, self.invoice_row_id],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "version": 9,
        }
        return {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": "withdraw_relation:CASE-RAW-OA:9",
            "active_relation": {"case_id": "CASE-RAW-OA", "version": 9},
            "before_relations": [active_relation],
            "after_relations": [],
            "submit_expected_versions": {"relation:CASE-RAW-OA": 9},
        }

    def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        self.withdraw_calls.append(dict(kwargs))
        restored_relation = {
            "case_id": "CASE-RESTORED",
            "row_ids": [self.raw_oa_row_id, self.bank_row_id, self.invoice_row_id],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "version": 4,
        }
        return {
            "status": "withdrawn",
            "relation": {
                "case_id": "CASE-RAW-OA",
                "row_ids": [self.raw_oa_row_id, self.bank_row_id, self.invoice_row_id],
                "status": "cancelled",
                "version": 10,
            },
            "history": {"operation_type": "withdraw_link"},
            "changed_case_ids": ["CASE-RAW-OA", "CASE-RESTORED"],
            "affected_months": ["2026-05"],
            "affected_row_ids": [self.raw_oa_row_id, self.bank_row_id, self.invoice_row_id],
            "restored_relations": [restored_relation],
            "version": 10,
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-05"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }


class _RawOaAliasSameRowsPreviewRelationCommandService(_RawOaAliasWithdrawRelationCommandService):
    def preview_withdraw_relation(self, **kwargs: object) -> dict[str, object]:
        preview = super().preview_withdraw_relation(**kwargs)
        preview["after_relations"] = [
            {
                "case_id": "CASE-SAME-RAW-OA",
                "row_ids": [self.raw_oa_row_id, self.bank_row_id, self.invoice_row_id],
                "row_types": ["oa", "bank", "invoice"],
                "status": "active",
                "relation_mode": "manual_confirmed",
                "month_scope": "2026-05",
                "version": 4,
                "special_metadata": {"restorable_on_withdraw": True},
            }
        ]
        return preview


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
    override_service: object | None = None,
    live_rows: list[dict[str, object]] | None = None,
    relation_groups: object | None = None,
    withdraw_rows_and_after_relations: object | None = None,
    scope_keys_for_row_ids: object | None = None,
    scope_keys_for_rows: object | None = None,
    resolve_rows_for_amount_check: object | None = None,
    resolve_live_rows_direct: object | None = None,
    resolved_row_types_for_row_ids: object | None = None,
    pair_relation_service: object | None = None,
    bank_transaction_category_codes_for_row_ids: object | None = None,
    bank_flow_rule_tag_rules_payload: object | None = None,
    list_ignored_rows: object | None = None,
) -> WorkbenchWriteFacade:
    resolved_pair_relation_service = pair_relation_service or _PairRelationService()
    return WorkbenchWriteFacade(
        relation_read_snapshot_port=WorkbenchWriteRelationReadSnapshotPort(resolved_pair_relation_service),
        relation_special_metadata_mutation_port=WorkbenchWriteRelationSpecialMetadataMutationPort(
            resolved_pair_relation_service
        ),
        exception_service=object(),
        exception_case_service=exception_case_service or object(),
        override_service=override_service or object(),
        next_case_id=lambda: "CASE-NEW",
        normalize_row_ids=lambda values: [str(value) for value in values],
        resolved_row_types_for_row_ids=resolved_row_types_for_row_ids or (
            lambda row_ids, **_: ["oa" if str(row_id).startswith("oa") else "bank" for row_id in row_ids]
        ),
        can_confirm_link_row_types=lambda **_: True,
        expand_confirm_link_row_ids_for_existing_context=lambda row_ids, **_: list(row_ids),
        resolve_rows_for_amount_check=resolve_rows_for_amount_check or (lambda row_ids, **_: [{"id": row_id} for row_id in row_ids]),
        merge_relation_snapshots=lambda before, synthetic: list(before) + list(synthetic),
        synthetic_existing_case_relations=lambda *_, **__: [],
        month_scope_for_selected_row_ids=lambda **_: "2026-05",
        scope_keys_for_row_ids=scope_keys_for_row_ids or (lambda **_: {"2026-05"}),
        scope_keys_for_rows=scope_keys_for_rows or (lambda rows, **_: ["2026-05"]),
        resolve_live_rows_direct=resolve_live_rows_direct or (lambda *_, **__: list(live_rows or [])),
        relation_groups=relation_groups or (lambda *_, **__: []),
        withdraw_rows_and_after_relations=withdraw_rows_and_after_relations or (lambda *_, **__: ([], [], [])),
        amount_check_for_rows_by_type=lambda _: {},
        transaction_amount_for_row_id=lambda _: 0,
        list_ignored_rows=list_ignored_rows or (lambda *_, **__: []),
        save_exception_cases_snapshot=lambda: None,
        persist_pair_relations=lambda **_: None,
        save_overrides_snapshot=lambda **_: None,
        restore_exception_write_snapshots=lambda **_: None,
        restore_exception_override_snapshots=lambda **_: None,
        restore_exception_pair_snapshots=lambda **_: None,
        schedule_pair_relation_persist=lambda **_: None,
        restore_pair_relation_snapshot=lambda *_, **__: None,
        emit_action_timing=lambda **_: None,
        confirm_link_uow=confirm_uow,
        cancel_link_uow=cancel_uow,
        withdraw_link_uow=withdraw_uow,
        persist_pair_relations_in_transaction=lambda **_: None,
        bank_transaction_category_codes_for_row_ids=bank_transaction_category_codes_for_row_ids,
        bank_flow_rule_tag_rules_payload=bank_flow_rule_tag_rules_payload,
        relation_command_service=relation_command_service,
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
    def test_ignore_row_resolves_one_canonical_row_without_building_page_payload(self) -> None:
        resolver_calls: list[dict[str, object]] = []

        class ExceptionCases:
            @staticmethod
            def snapshot() -> dict[str, object]:
                return {}

            @staticmethod
            def ignore_row(row: dict[str, object], *, comment: str | None = None) -> dict[str, object]:
                return {"id": "EX-1", "row_id": row["id"], "comment": comment}

        class Overrides:
            @staticmethod
            def snapshot() -> dict[str, object]:
                return {}

            @staticmethod
            def ignore_row(
                *,
                row: dict[str, object],
                comment: str | None = None,
                exception_case_id: str | None = None,
            ) -> dict[str, object]:
                return {**row, "ignored": True, "comment": comment, "exception_case_id": exception_case_id}

        def resolve_rows(row_ids: list[str], *, month_hint: str | None = None) -> list[dict[str, object]]:
            resolver_calls.append({"row_ids": row_ids, "month_hint": month_hint})
            return [{"id": row_ids[0], "type": "invoice", "issue_date": "2026-05-01"}]

        facade = _new_facade(
            exception_case_service=ExceptionCases(),
            override_service=Overrides(),
            resolve_live_rows_direct=resolve_rows,
        )

        result = facade.ignore_row({"month": "2026-05", "row_id": "invoice-1", "comment": "test"})

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_row_ids"], ["invoice-1"])
        self.assertEqual(resolver_calls, [{"row_ids": ["invoice-1"], "month_hint": "2026-05"}])

    def test_unignore_row_uses_injected_narrow_ignored_row_loader(self) -> None:
        loader_calls: list[str] = []

        class ExceptionCases:
            @staticmethod
            def snapshot() -> dict[str, object]:
                return {}

            @staticmethod
            def unignore_row(row: dict[str, object]) -> dict[str, object]:
                return {"id": "EX-1", "row_id": row["id"]}

        class Overrides:
            @staticmethod
            def snapshot() -> dict[str, object]:
                return {}

            @staticmethod
            def unignore_row(*, row: dict[str, object]) -> dict[str, object]:
                return {**row, "ignored": False}

        def list_ignored_rows(month: str) -> list[dict[str, object]]:
            loader_calls.append(month)
            return [{"id": "invoice-1", "type": "invoice", "issue_date": "2026-05-01"}]

        facade = _new_facade(
            exception_case_service=ExceptionCases(),
            override_service=Overrides(),
            list_ignored_rows=list_ignored_rows,
        )

        result = facade.unignore_row({"month": "2026-05", "row_id": "invoice-1"})

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_row_ids"], ["invoice-1"])
        self.assertEqual(loader_calls, ["2026-05"])

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

    def test_confirm_link_response_returns_zero_downstream_freshness_targets(self) -> None:
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
        self.assertEqual(result.payload["freshness_targets"], [])

    def test_confirm_link_two_pane_operation_projection_uses_group_zone(self) -> None:
        def relation_groups(relations: list[dict[str, object]], **_: object) -> list[dict[str, object]]:
            relation = relations[0]
            return [
                {
                    "group_id": f"case:{relation['case_id']}",
                    "group_type": relation["relation_mode"],
                    "zone": "unpaired",
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
                "idempotency_key": "confirm:two-pane-paired-projection",
            },
            request_id="req-confirm-two-pane-paired-projection",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        projection_after = result.payload["operation_projection"]["after"]
        self.assertEqual(projection_after["paired_groups"], [])
        self.assertEqual(projection_after["unpaired_groups"][0]["group_id"], "case:CASE-NEW")

    def test_confirm_link_three_pane_operation_projection_uses_paired_groups(self) -> None:
        def relation_groups(relations: list[dict[str, object]], **_: object) -> list[dict[str, object]]:
            relation = relations[0]
            return [
                {
                    "group_id": f"case:{relation['case_id']}",
                    "group_type": relation["relation_mode"],
                    "zone": "paired",
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
        self.assertEqual(projection_after["unpaired_groups"], [])
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
        self.assertEqual(result.payload["freshness_targets"], [])

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

    def test_withdraw_link_uow_path_does_not_read_legacy_pair_snapshot(self) -> None:
        facade = _new_facade(
            withdraw_uow=_RecordingUoW(),
            relation_command_service=_RecordingRelationCommandService(),
            pair_relation_service=_SnapshotForbiddenPairRelationService(),
        )

        result = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "withdraw:no-legacy-snapshot",
            },
            request_id="req-withdraw-no-snapshot",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-05"])

    def test_confirm_link_uow_path_does_not_read_legacy_pair_snapshot(self) -> None:
        facade = _new_facade(
            confirm_uow=_RecordingUoW(),
            relation_command_service=_RecordingRelationCommandService(),
            pair_relation_service=_SnapshotForbiddenPairRelationService(),
        )

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:no-legacy-snapshot",
            },
            request_id="req-confirm-no-snapshot",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-05"])

    def test_confirm_link_uow_reuses_one_paired_policy_metadata_snapshot(self) -> None:
        rule_reads: list[bool] = []
        relation_command = _RecordingRelationCommandService()
        facade = _new_facade(
            confirm_uow=_HandlerCallingUoW(),
            relation_command_service=relation_command,
            resolve_rows_for_amount_check=lambda row_ids, **_: [
                {"id": row_id, "type": "oa" if row_id.startswith("oa") else "bank"}
                for row_id in row_ids
            ],
            bank_transaction_category_codes_for_row_ids=lambda row_ids: {
                row_id: "external_turnover" for row_id in row_ids
            },
            bank_flow_rule_tag_rules_payload=lambda: (
                rule_reads.append(True)
                or {
                    "version": 3,
                    "rules": [
                        {
                            "tag_code": "external_turnover",
                            "requires_oa": True,
                            "requires_invoice": False,
                        }
                    ],
                }
            ),
        )

        result = facade.confirm_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "confirm:single-policy-snapshot",
            },
            request_id="req-confirm-single-policy",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(len(rule_reads), 1)
        metadata = relation_command.confirm_calls[0]["special_metadata"]
        self.assertEqual(metadata["paired_requirement_version"], 3)
        self.assertFalse(metadata["requires_invoice"])

    def test_withdraw_link_response_returns_zero_downstream_freshness_targets(self) -> None:
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
        self.assertEqual(result.payload["freshness_targets"], [])

    def test_withdraw_link_submit_skips_optional_operation_projection_rebuild(self) -> None:
        def forbidden_projection_rebuild(**_kwargs: object) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
            raise AssertionError("withdraw submit must not rebuild optional operation projection")

        facade = _new_facade(
            withdraw_uow=_RecordingUoW(),
            relation_command_service=_RecordingRelationCommandService(),
            withdraw_rows_and_after_relations=forbidden_projection_rebuild,
        )

        result = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "withdraw:no-submit-projection",
            },
            request_id="req-withdraw-no-submit-projection",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["operation_projection"], {})
        self.assertEqual(result.payload["freshness_targets"], [])

    def test_withdraw_link_uow_submit_reuses_alias_map_in_postprocess(self) -> None:
        resolve_calls: list[dict[str, object]] = []

        def resolve_live_rows_direct(row_ids: list[str], **kwargs: object) -> list[dict[str, object]]:
            resolve_calls.append({"row_ids": list(row_ids), **kwargs})
            return [
                {"id": "oa-1", "type": "oa", "summary_fields": {"申请日期": "2026-05-10"}},
                {"id": "bank-1", "type": "bank", "trade_time": "2026-05-10 10:00:00"},
            ]

        facade = _new_facade(
            withdraw_uow=_RecordingUoW(),
            relation_command_service=_RecordingRelationCommandService(),
            resolve_live_rows_direct=resolve_live_rows_direct,
        )

        result = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["oa-1", "bank-1"],
                "idempotency_key": "withdraw:single-alias-map",
            },
            request_id="req-withdraw-single-alias-map",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(resolve_calls, [{"row_ids": ["oa-1", "bank-1"], "month_hint": "2026-05"}])

    def test_withdraw_link_bank_invoice_submit_does_not_resolve_live_rows_for_metadata(self) -> None:
        class _BankInvoiceWithdrawRelationCommandService(_RecordingRelationCommandService):
            def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                before_relation = {
                    "case_id": "CASE-BANK-INVOICE",
                    "row_ids": ["bank-1", "invoice-1"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "month_scope": "2026-05",
                    "version": 3,
                }
                return {
                    "status": "withdrawn",
                    "relation": {**before_relation, "status": "cancelled", "version": 4},
                    "before_relation": before_relation,
                    "history": {"operation_type": "withdraw_link"},
                    "changed_case_ids": ["CASE-BANK-INVOICE"],
                    "affected_months": ["2026-05"],
                    "affected_row_ids": ["bank-1", "invoice-1"],
                    "restored_relations": [],
                    "version": 4,
                    "read_model_status": "fresh",
                    "read_model_stale_reasons": [],
                    "read_model_scope_keys": ["2026-05"],
                    "refresh_enqueued": False,
                    "idempotent_replay": False,
                }

        def forbidden_live_rows(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
            raise AssertionError("bank+invoice withdraw submit must not synchronously resolve live rows.")

        facade = _new_facade(
            withdraw_uow=_RecordingUoW(),
            relation_command_service=_BankInvoiceWithdrawRelationCommandService(),
            resolve_live_rows_direct=forbidden_live_rows,
        )

        result = facade.withdraw_link(
            {
                "month": "2026-05",
                "row_ids": ["bank-1", "invoice-1"],
                "idempotency_key": "withdraw:bank-invoice-no-live-rows",
            },
            request_id="req-withdraw-bank-invoice-no-live-rows",
            actor_id="oa-user-1",
            tenant_id="default",
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-05"])

    def test_withdraw_link_targets_preview_row_months_when_relation_scope_is_all(self) -> None:
        class _AllScopeWithdrawRelationCommandService(_RecordingRelationCommandService):
            def withdraw_relation(self, **kwargs: object) -> dict[str, object]:
                self.withdraw_calls.append(dict(kwargs))
                active_relation = {
                    "case_id": "CASE-ALL",
                    "row_ids": list(kwargs["row_ids"]),
                    "row_types": ["oa", "bank", "bank"],
                    "status": "active",
                    "month_scope": "all",
                    "version": 7,
                }
                return {
                    "status": "withdrawn",
                    "relation": {**active_relation, "status": "cancelled", "version": 8},
                    "before_relation": active_relation,
                    "history": {"operation_type": "withdraw_link"},
                    "changed_case_ids": ["CASE-ALL"],
                    "affected_months": ["all"],
                    "affected_row_ids": list(kwargs["row_ids"]),
                    "restored_relations": [],
                    "version": 8,
                    "read_model_status": "fresh",
                    "read_model_stale_reasons": [],
                    "read_model_scope_keys": ["all"],
                    "refresh_enqueued": False,
                    "idempotent_replay": False,
                }

        uow = _RecordingUoW()
        row_ids = ["oa-imported-2048", "txn_imported_1361", "txn_imported_1269"]
        preview_rows = [
            {"id": "oa-imported-2048", "type": "oa", "summary_fields": {"申请日期": "2026-03-09"}},
            {"id": "txn_imported_1361", "type": "bank", "trade_time": "2026-03-09 12:06:30"},
            {"id": "txn_imported_1269", "type": "bank", "trade_time": "2026-02-03 09:16:49"},
        ]
        relation_command = _AllScopeWithdrawRelationCommandService()
        facade = _new_facade(
            withdraw_uow=uow,
            relation_command_service=relation_command,
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
        self.assertEqual(getattr(uow.run_commands[0], "scope_keys"), [])
        self.assertEqual(len(relation_command.preview_withdraw_calls), 0)
        self.assertEqual(relation_command.withdraw_calls[0]["row_ids"], row_ids)
        self.assertEqual(result.payload["affected_scope_keys"], ["2026-03", "2026-02"])
        self.assertEqual(result.payload["freshness_targets"], [])

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

    def test_confirm_link_uow_preserves_relation_command_freshness_error(self) -> None:
        facade = _new_facade(
            confirm_uow=_HandlerCallingUoW(),
            relation_command_service=_StaleConfirmRelationCommandService(),
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
        self.assertEqual(result.payload["error"], "workbench_relation_read_model_not_fresh")
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["dirty_scope_pending"])
        self.assertEqual(result.payload["read_model_scope_keys"], ["2026-05"])
        self.assertTrue(result.payload["refresh_enqueued"])

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

    def test_withdraw_link_canonicalizes_legacy_oa_source_ids_and_drops_same_row_restore(self) -> None:
        relation_command = _RawOaAliasWithdrawRelationCommandService()
        selected_row_ids = [
            relation_command.canonical_oa_row_id,
            relation_command.bank_row_id,
            relation_command.invoice_row_id,
        ]
        live_rows = [
            {
                "id": relation_command.canonical_oa_row_id,
                "type": "oa",
                "amount": "145.00",
                "detail_fields": {
                    "Mongo文档ID": "69fab21659b12d7d42a50a45",
                    "OA单号": "2156",
                },
            },
            {"id": relation_command.bank_row_id, "type": "bank", "amount": "145.00"},
            {"id": relation_command.invoice_row_id, "type": "invoice", "amount": "145.00"},
        ]
        resolved_active_row_ids: list[list[str]] = []

        def withdraw_rows_and_after_relations(**kwargs: object) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
            active_relation = dict(kwargs["active_relation"])
            resolved_active_row_ids.append(list(active_relation.get("row_ids") or []))
            return live_rows, list(kwargs.get("after_relations") or []), list(active_relation.get("row_ids") or [])

        facade = _new_facade(
            relation_command_service=relation_command,
            live_rows=live_rows,
            scope_keys_for_row_ids=lambda **_: {"all"},
            withdraw_rows_and_after_relations=withdraw_rows_and_after_relations,
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": selected_row_ids,
            }
        )
        submit = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": selected_row_ids,
                "operation_type": "withdraw_relation",
                "preview_id": preview.payload["preview_id"],
                "expected_versions": preview.payload["submit_expected_versions"],
                "idempotency_key": "withdraw:raw-oa-alias",
            },
            request_id="req-withdraw-raw-oa-alias",
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        self.assertEqual(submit.status_code, HTTPStatus.OK)
        self.assertTrue(resolved_active_row_ids)
        self.assertTrue(all(row_ids == selected_row_ids for row_ids in resolved_active_row_ids))
        self.assertEqual(submit.payload["affected_row_ids"], selected_row_ids)
        self.assertEqual(submit.payload["restored_relations"], [])
        self.assertNotIn(relation_command.raw_oa_row_id, submit.payload["affected_row_ids"])

    def test_withdraw_preview_filters_same_canonical_alias_after_relation(self) -> None:
        relation_command = _RawOaAliasSameRowsPreviewRelationCommandService()
        selected_row_ids = [
            relation_command.canonical_oa_row_id,
            relation_command.bank_row_id,
            relation_command.invoice_row_id,
        ]
        live_rows = [
            {
                "id": relation_command.canonical_oa_row_id,
                "type": "oa",
                "amount": "145.00",
                "detail_fields": {
                    "Mongo文档ID": "69fab21659b12d7d42a50a45",
                    "OA单号": "2156",
                },
            },
            {"id": relation_command.bank_row_id, "type": "bank", "amount": "145.00"},
            {"id": relation_command.invoice_row_id, "type": "invoice", "amount": "145.00"},
        ]
        facade = _new_facade(
            relation_command_service=relation_command,
            live_rows=live_rows,
            relation_groups=_preview_relation_groups(),
            withdraw_rows_and_after_relations=lambda **_: (live_rows, [], selected_row_ids),
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": selected_row_ids,
            }
        )

        self.assertEqual(preview.status_code, HTTPStatus.OK)
        after_groups = preview.payload["after"]["groups"]
        self.assertEqual(
            [str(group["reason"]) for group in after_groups],
            ["selected_row", "selected_row", "selected_row"],
        )
        self.assertEqual(
            [str(group["group_id"]) for group in after_groups],
            [f"selected:{row_id}" for row_id in selected_row_ids],
        )
        self.assertEqual(preview.payload["restored_relations"], [])
        self.assertEqual(
            relation_command.preview_withdraw_calls[0]["row_id_aliases"].get(relation_command.raw_oa_row_id),
            relation_command.canonical_oa_row_id,
        )

    def test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually(self) -> None:
        relation_command = _BankInvoiceWithdrawRelationCommandService()
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
            relation_groups=_preview_relation_groups(),
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

    def test_withdraw_link_rejects_standalone_rows_without_active_relation(self) -> None:
        facade = _new_facade(
            relation_command_service=_NoActiveRelationCommandService(),
            live_rows=[
                {"id": "oa-standalone", "type": "oa", "amount": "100.00"},
                {"id": "bank-standalone", "type": "bank", "amount": "100.00"},
                {"id": "invoice-standalone", "type": "invoice", "amount": "100.00"},
            ],
        )

        preview = facade.preview_withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-standalone"],
            }
        )
        submit = facade.withdraw_link(
            {
                "month": "all",
                "row_ids": ["bank-standalone"],
                "operation_type": "withdraw_relation",
                "idempotency_key": "withdraw-standalone:1",
            },
            request_id="req-withdraw-standalone",
        )

        self.assertEqual(preview.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(preview.payload["error"], "workbench_relation_not_found")
        self.assertEqual(submit.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(submit.payload["error"], "workbench_relation_not_found")

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

    def test_personal_advance_repayment_rejects_unbalanced_canonical_rows(self) -> None:
        rows = _personal_advance_rows()
        rows[-1]["credit_amount"] = "999.99"
        facade = _new_facade(
            relation_command_service=_RecordingRelationCommandService(),
            exception_case_service=_RecordingExceptionCaseService(),
            live_rows=rows,
        )

        result = facade.confirm_personal_advance_repayment(
            {"month": "2026-05", "row_ids": [str(row["id"]) for row in rows]},
            request_id="req-personal-advance-unbalanced",
        )

        self.assertEqual(result.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(result.payload["error"], "invalid_personal_advance_repayment_request")
        self.assertEqual(result.payload["amount_summary"]["bank_credit_total"], "999.99")

    def test_personal_advance_repayment_requires_both_bank_directions(self) -> None:
        for removed_row_id, expected_message in (
            ("bank-advance-in", "bank credit"),
            ("bank-advance-out", "bank debit"),
        ):
            with self.subTest(removed_row_id=removed_row_id):
                rows = [row for row in _personal_advance_rows() if row["id"] != removed_row_id]
                facade = _new_facade(
                    relation_command_service=_RecordingRelationCommandService(),
                    exception_case_service=_RecordingExceptionCaseService(),
                    live_rows=rows,
                )

                result = facade.confirm_personal_advance_repayment(
                    {"month": "2026-05", "row_ids": [str(row["id"]) for row in rows]},
                    request_id=f"req-personal-advance-{removed_row_id}",
                )

                self.assertEqual(result.status_code, HTTPStatus.BAD_REQUEST)
                self.assertIn(expected_message, str(result.payload["message"]))

    def test_personal_advance_repayment_rejects_invoice_canonical_row(self) -> None:
        rows = [*_personal_advance_rows(), {"id": "invoice-advance-1", "type": "invoice", "amount": "1000.00"}]
        row_types = {str(row["id"]): str(row["type"]) for row in rows}
        facade = _new_facade(
            relation_command_service=_RecordingRelationCommandService(),
            exception_case_service=_RecordingExceptionCaseService(),
            live_rows=rows,
            resolved_row_types_for_row_ids=lambda row_ids, **_: [row_types[str(row_id)] for row_id in row_ids],
        )

        result = facade.confirm_personal_advance_repayment(
            {"month": "2026-05", "row_ids": [str(row["id"]) for row in rows]},
            request_id="req-personal-advance-invoice",
        )

        self.assertEqual(result.status_code, HTTPStatus.BAD_REQUEST)
        self.assertIn("invoice rows", str(result.payload["message"]))

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
        app._workbench_write_freshness_guard = lambda _payload: None

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
