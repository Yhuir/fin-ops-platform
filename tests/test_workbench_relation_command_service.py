from __future__ import annotations

from copy import deepcopy
import unittest

from fin_ops_platform.services.workbench_relation_command_service import (
    VALID_WORKBENCH_RELATION_MODES,
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class FakeRelationRepository:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self.snapshot = deepcopy(snapshot or {})
        self.load_calls = 0
        self.scoped_load_calls: list[dict[str, object]] = []
        self.active_case_load_calls: list[str] = []
        self.save_calls: list[dict[str, object]] = []
        self.lock_calls: list[dict[str, object]] = []

    def load_workbench_pair_relations(self) -> dict[str, object]:
        self.load_calls += 1
        return deepcopy(self.snapshot)

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, object]:
        self.scoped_load_calls.append(
            {
                "row_ids": list(row_ids or []),
                "case_ids": list(case_ids or []),
            }
        )
        return WorkbenchPairRelationService.from_snapshot(
            self.snapshot
        ).snapshot_for_row_ids(list(row_ids or []), case_ids=list(case_ids or []))

    def load_active_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, object]:
        self.scoped_load_calls.append(
            {
                "row_ids": list(row_ids or []),
                "case_ids": list(case_ids or []),
            }
        )
        normalized_row_ids = set(row_ids or [])
        normalized_case_ids = set(case_ids or [])
        relations = {
            case_id: deepcopy(relation)
            for case_id, relation in dict(self.snapshot.get("pair_relations") or {}).items()
            if isinstance(relation, dict)
            and relation.get("status") == "active"
            and (
                case_id in normalized_case_ids
                or normalized_row_ids.intersection(relation.get("row_ids") or [])
            )
        }
        return {"pair_relations": relations}

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: set[str] | None = None,
    ) -> None:
        self.save_calls.append(
            {
                "snapshot": deepcopy(snapshot),
                "changed_case_ids": set(changed_case_ids or set()),
            }
        )
        self.snapshot = deepcopy(snapshot)

    def save_workbench_pair_relation_delta(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        normalized_case_ids = set(changed_case_ids or set())
        self.save_calls.append(
            {
                "snapshot": deepcopy(snapshot),
                "changed_case_ids": normalized_case_ids,
            }
        )
        service = WorkbenchPairRelationService.from_snapshot(self.snapshot)
        service.apply_snapshot_delta(
            snapshot,
            changed_case_ids=normalized_case_ids,
            replace_history=False,
        )
        self.snapshot = service.snapshot()

    def load_active_workbench_pair_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        self.active_case_load_calls.append(case_id)
        relation = dict(self.snapshot.get("pair_relations") or {}).get(case_id)
        return deepcopy(relation) if isinstance(relation, dict) and relation.get("status") == "active" else None

    def acquire_relation_member_locks(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> list[str]:
        self.lock_calls.append(
            {
                "row_ids": list(row_ids or []),
                "row_types": list(row_types or []),
                "case_ids": list(case_ids or []),
            }
        )
        return list(row_ids or [])


class FakeRelationFacade:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "read_model_scope_keys": ["2026-05"],
            "stale_reasons": [],
            "refresh_enqueued": False,
        }
        self.calls: list[dict[str, object]] = []

    def get_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "row_ids": list(row_ids),
                "require_fresh": require_fresh,
                "reason": reason,
                "month_hint": month_hint,
                "scope_keys_hint": list(scope_keys_hint or []),
            }
        )
        return deepcopy(self.payload)


class WorkbenchRelationCommandServiceTests(unittest.TestCase):
    def test_active_relation_case_lookup_uses_narrow_repository_boundary(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "CASE-1": {
                        "case_id": "CASE-1",
                        "row_ids": ["bank-1"],
                        "row_types": ["bank"],
                        "status": "active",
                    }
                },
                "pair_relation_history": [
                    {"operation_type": "old-1", "after_relations": [{"case_id": "CASE-1"}]},
                ],
            }
        )
        service = WorkbenchRelationCommandService(relation_repository=repository)

        relation = service.get_active_relation_by_case_id("CASE-1")

        self.assertEqual(relation["row_ids"], ["bank-1"])
        self.assertEqual(repository.active_case_load_calls, ["CASE-1"])
        self.assertEqual(repository.scoped_load_calls, [])

    def test_write_precondition_preserves_explicit_cross_month_scope_hints(self) -> None:
        facade = FakeRelationFacade(
            {
                "status": "fresh",
                "rows": [],
                "groups": [],
                "read_model_scope_keys": ["2026-04", "2026-06"],
                "stale_reasons": [],
                "refresh_enqueued": False,
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=FakeRelationRepository(),
            relation_facade=facade,
            require_fresh_relations=True,
        )

        result = service.assert_write_precondition(
            row_ids=["bank-april", "bank-june"],
            month_scope="all",
            scope_keys_hint=["2026-04", "2026-06", "2026-04"],
        )

        self.assertEqual(result["status"], "fresh")
        self.assertEqual(facade.calls[0]["month_hint"], "all")
        self.assertEqual(facade.calls[0]["scope_keys_hint"], ["2026-04", "2026-06"])

    def test_confirm_relation_uses_scoped_relation_snapshot_for_target_rows(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "unrelated": {
                        "case_id": "unrelated",
                        "row_ids": ["bank-unrelated"],
                        "row_types": ["bank"],
                        "status": "active",
                    }
                }
            }
        )
        service = WorkbenchRelationCommandService(relation_repository=repository)

        result = service.confirm_relation(
            case_id="case-new",
            row_ids=["bank-1", "oa-1"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(repository.load_calls, 0)
        self.assertEqual(
            repository.scoped_load_calls[0],
            {"row_ids": ["bank-1", "oa-1"], "case_ids": ["case-new"]},
        )
        self.assertEqual(repository.save_calls[-1]["changed_case_ids"], {"case-new"})

    def test_confirm_relation_saves_only_new_history_event(self) -> None:
        historical_events = [
            {
                "operation_id": f"old-{index}",
                "operation_type": "old-confirm",
                "after_relations": [{"case_id": "case-new"}],
            }
            for index in range(25)
        ]
        repository = FakeRelationRepository({"pair_relation_history": historical_events})
        service = WorkbenchRelationCommandService(relation_repository=repository)

        result = service.confirm_relation(
            case_id="case-new",
            row_ids=["bank-1", "oa-1"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
        )

        saved_history = repository.save_calls[-1]["snapshot"]["pair_relation_history"]
        self.assertEqual(saved_history, [result["history"]])
        self.assertEqual(len(repository.snapshot["pair_relation_history"]), 26)

    def test_prepared_confirm_reuses_freshness_locks_and_scoped_snapshot(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-oa": {
                        "case_id": "case-oa",
                        "row_ids": ["oa-1", "bank-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                    }
                },
                "pair_relation_history": [
                    {
                        "operation_id": f"old-case-oa-{index}",
                        "operation_type": "old-confirm",
                        "after_relations": [{"case_id": "case-oa"}],
                    }
                    for index in range(25)
                ],
            }
        )
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        preparation = service.prepare_confirm_relation(
            row_ids=["bank-1"],
            row_types=["bank"],
            month_scope="2026-05",
            scope_keys_hint=["2026-05"],
        )
        result = service.confirm_relation(
            case_id="turnover:case-1",
            row_ids=["oa-1", "bank-1"],
            row_types=["oa", "bank"],
            relation_mode="turnover_manual_closure",
            actor_id="finance-user",
            month_scope="2026-05",
            before_relations=list(preparation.active_relations),
            replace_existing=True,
            preparation=preparation,
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(repository.scoped_load_calls, [{"row_ids": ["bank-1"], "case_ids": []}])
        self.assertEqual(
            repository.save_calls[-1]["snapshot"]["pair_relation_history"],
            [result["history"]],
        )
        self.assertEqual(
            repository.lock_calls,
            [
                {"row_ids": ["bank-1"], "row_types": ["bank"], "case_ids": []},
                {"row_ids": ["oa-1"], "row_types": ["oa"], "case_ids": ["turnover:case-1"]},
            ],
        )

    def test_prepared_confirm_rejects_rows_outside_prepared_snapshot(self) -> None:
        service = WorkbenchRelationCommandService(
            relation_repository=FakeRelationRepository(),
            relation_facade=FakeRelationFacade(),
            require_fresh_relations=True,
        )
        preparation = service.prepare_confirm_relation(
            row_ids=["bank-1"],
            row_types=["bank"],
            month_scope="2026-05",
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="turnover:case-1",
                row_ids=["bank-1", "oa-unprepared"],
                row_types=["bank", "oa"],
                relation_mode="turnover_manual_closure",
                actor_id="finance-user",
                month_scope="2026-05",
                preparation=preparation,
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_preparation_conflict")

    def test_preview_withdraw_relation_returns_locked_previous_state(self) -> None:
        previous_relation = {
            "case_id": "case-old",
            "row_ids": ["oa-1", "bank-1"],
            "row_types": ["oa", "bank"],
            "status": "cancelled",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-01T10:00:00+00:00",
            "updated_at": "2026-05-01T10:00:00+00:00",
            "version": 1,
            "special_metadata": {"restorable_on_withdraw": True},
        }
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["oa-1", "bank-1", "invoice-1"],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-old": previous_relation,
                    "case-new": active_relation,
                },
                "pair_relation_history": [
                    {
                        "operation_id": "hist-confirm-new",
                        "operation_type": "confirm_link",
                        "before_relations": [previous_relation],
                        "after_relations": [active_relation],
                        "affected_row_ids": ["oa-1", "bank-1", "invoice-1"],
                        "created_by": "finance-user",
                        "created_at": "2026-05-02T10:00:00+00:00",
                    }
                ],
            }
        )
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        preview = service.preview_withdraw_relation(
            row_ids=["invoice-1"],
            month_scope="2026-05",
        )

        self.assertEqual(preview["operation_type"], "withdraw_relation")
        self.assertTrue(str(preview["preview_id"]).startswith("withdraw_relation:"))
        self.assertEqual(preview["active_relation"]["case_id"], "case-new")
        self.assertEqual(preview["before_relations"][0]["case_id"], "case-new")
        self.assertEqual(preview["after_relations"][0]["case_id"], "case-old")
        self.assertEqual(preview["submit_expected_versions"], {"relation:case-new": 2})
        self.assertEqual(facade.calls[0]["row_ids"], ["oa-1", "bank-1", "invoice-1"])
        self.assertEqual(facade.calls[0]["scope_keys_hint"], ["2026-05"])
        self.assertEqual(repository.save_calls, [])

    def test_preview_withdraw_relation_blocks_plain_oa_attachment_binding(self) -> None:
        invoice_id = "oa-att-inv-oa-exp-69fab21659b12d7d42a50a45:item:0:fb2a9c9fab23-b515bf77d490fdfe"
        active_relation = {
            "case_id": "CASE-OA-ATT-oa-exp-2156",
            "row_ids": ["oa-exp-2156", invoice_id],
            "row_types": ["oa", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
            "special_metadata": {
                "source": "oa_attachment_invoice",
                "parent_oa_row_id": "oa-exp-2156",
                "immutable_oa_attachment_binding": True,
                "contains_immutable_oa_attachment_binding": True,
            },
        }
        repository = FakeRelationRepository(
            {"pair_relations": {"CASE-OA-ATT-oa-exp-2156": active_relation}}
        )
        facade = FakeRelationFacade({"status": "stale", "read_model_scope_keys": ["2026-05"]})
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        preview = service.preview_withdraw_relation(
            row_ids=["oa-exp-2156", invoice_id],
            month_scope="2026-05",
        )

        self.assertFalse(preview["can_submit"])
        self.assertIn("无法撤回", preview["message"])
        self.assertEqual(preview["before_relations"][0]["row_ids"], active_relation["row_ids"])
        self.assertEqual(preview["after_relations"][0]["row_ids"], active_relation["row_ids"])
        self.assertEqual(preview["submit_expected_versions"], {"relation:CASE-OA-ATT-oa-exp-2156": 2})
        self.assertEqual(facade.calls, [])
        self.assertEqual(repository.save_calls, [])

    def test_withdraw_relation_rejects_plain_oa_attachment_binding_submit(self) -> None:
        active_relation = {
            "case_id": "CASE-OA-ATT-oa-exp-2066-2",
            "row_ids": ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
            "row_types": ["oa", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository(
            {"pair_relations": {"CASE-OA-ATT-oa-exp-2066-2": active_relation}}
        )
        service = WorkbenchRelationCommandService(relation_repository=repository)

        with self.assertRaises(WorkbenchRelationCommandError) as raised:
            service.withdraw_relation(
                case_id="CASE-OA-ATT-oa-exp-2066-2",
                actor_id="finance-user",
                operation_type="withdraw_relation",
            )

        self.assertEqual(raised.exception.error_code, "workbench_relation_immutable_oa_attachment_binding")
        self.assertIn("无法撤回", raised.exception.message)
        self.assertEqual(repository.save_calls, [])

    def test_withdraw_relation_uses_canonical_relation_when_distribution_is_stale_by_default(self) -> None:
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["bank-1", "invoice-1"],
            "row_types": ["bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository({"pair_relations": {"case-new": active_relation}})
        facade = FakeRelationFacade(
            {
                "status": "stale",
                "rows": [],
                "groups": [],
                "read_model_scope_keys": ["2026-05"],
                "stale_reasons": ["dirty_scope:2026-05"],
                "refresh_enqueued": True,
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
        )

        preview = service.preview_withdraw_relation(
            row_ids=["invoice-1"],
            month_scope="2026-05",
        )
        result = service.withdraw_relation(
            case_id="case-new",
            actor_id="finance-user",
            reason="controlled withdraw",
            preview_id=str(preview["preview_id"]),
            operation_type="withdraw_relation",
            expected_versions=dict(preview["submit_expected_versions"]),
        )

        self.assertEqual(result["status"], "withdrawn")
        self.assertEqual(result["relation"]["status"], "cancelled")
        self.assertEqual(result["read_model_status"], "fresh")
        self.assertEqual(facade.calls, [])
        self.assertEqual(repository.save_calls[-1]["changed_case_ids"], {"case-new"})

    def test_withdraw_relation_submit_reuses_loaded_snapshot_for_preview_lock(self) -> None:
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["bank-1", "invoice-1"],
            "row_types": ["bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository({"pair_relations": {"case-new": active_relation}})
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        result = service.withdraw_relation(
            case_id="case-new",
            actor_id="finance-user",
            reason="controlled withdraw",
            operation_type="withdraw_relation",
        )

        self.assertEqual(result["status"], "withdrawn")
        self.assertEqual(repository.load_calls, 0)
        self.assertEqual(repository.scoped_load_calls[0], {"row_ids": [], "case_ids": ["case-new"]})
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(facade.calls[0]["row_ids"], ["bank-1", "invoice-1"])
        self.assertEqual(facade.calls[0]["scope_keys_hint"], ["2026-05"])
        self.assertEqual(repository.save_calls[-1]["changed_case_ids"], {"case-new"})

    def test_prepared_withdraw_reuses_lock_relation_snapshot_and_freshness(self) -> None:
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["bank-1", "bank-2"],
            "row_types": ["bank", "bank"],
            "status": "active",
            "relation_mode": "turnover_manual_closure",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository({"pair_relations": {"case-new": active_relation}})
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        preparation = service.prepare_withdraw_relation(case_id="case-new")
        result = service.withdraw_relation(
            case_id="case-new",
            actor_id="finance-user",
            reason="controlled withdraw",
            operation_type="withdraw_relation",
            preparation=preparation,
        )

        self.assertEqual(result["status"], "withdrawn")
        self.assertEqual(repository.scoped_load_calls, [{"row_ids": [], "case_ids": ["case-new"]}])
        self.assertEqual(
            repository.lock_calls,
            [{"row_ids": [], "row_types": [], "case_ids": ["case-new"]}],
        )
        self.assertEqual(len(facade.calls), 1)
        self.assertEqual(repository.save_calls[-1]["changed_case_ids"], {"case-new"})

    def test_prepared_withdraw_rejects_a_different_case(self) -> None:
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["bank-1", "bank-2"],
            "row_types": ["bank", "bank"],
            "status": "active",
            "relation_mode": "turnover_manual_closure",
            "month_scope": "2026-05",
            "version": 2,
        }
        service = WorkbenchRelationCommandService(
            relation_repository=FakeRelationRepository({"pair_relations": {"case-new": active_relation}})
        )
        preparation = service.prepare_withdraw_relation(case_id="case-new")

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.withdraw_relation(
                case_id="case-other",
                actor_id="finance-user",
                preparation=preparation,
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_preparation_conflict")

    def test_withdraw_relation_row_id_submit_fingerprint_distinguishes_row_ids(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-1": {
                        "case_id": "case-1",
                        "row_ids": ["bank-1", "invoice-1"],
                        "row_types": ["bank", "invoice"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                        "version": 2,
                    },
                    "case-2": {
                        "case_id": "case-2",
                        "row_ids": ["bank-2", "invoice-2"],
                        "row_types": ["bank", "invoice"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                        "version": 3,
                    },
                }
            }
        )
        service = WorkbenchRelationCommandService(relation_repository=repository)

        first = service.withdraw_relation(
            case_id="",
            row_ids=["bank-1", "invoice-1"],
            actor_id="finance-user",
            operation_type="withdraw_relation",
            idempotency_key="withdraw-row-id-submit",
        )
        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.withdraw_relation(
                case_id="",
                row_ids=["bank-2", "invoice-2"],
                actor_id="finance-user",
                operation_type="withdraw_relation",
                idempotency_key="withdraw-row-id-submit",
            )

        self.assertEqual(first["relation"]["case_id"], "case-1")
        self.assertEqual(context.exception.error_code, "workbench_relation_idempotency_conflict")
        self.assertEqual(len(repository.save_calls), 1)

    def test_withdraw_relation_rejects_stale_preview_identity(self) -> None:
        active_relation = {
            "case_id": "case-new",
            "row_ids": ["oa-1", "bank-1", "invoice-1"],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-02T10:00:00+00:00",
            "updated_at": "2026-05-02T10:00:00+00:00",
            "version": 2,
        }
        repository = FakeRelationRepository({"pair_relations": {"case-new": active_relation}})
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.withdraw_relation(
                case_id="case-new",
                actor_id="finance-user",
                preview_id="withdraw_relation:stale-preview",
                operation_type="withdraw_relation",
                expected_versions={"relation:case-old": 1},
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_preview_conflict")
        self.assertEqual(repository.save_calls, [])

    def test_confirm_relation_saves_changed_case_and_audit_history(self) -> None:
        repository = FakeRelationRepository()
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        result = service.confirm_relation(
            case_id="case-1",
            row_ids=["oa-1", "bank-1"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
            note="manual match",
            occurred_at="2026-05-02T10:00:00+00:00",
            idempotency_key="confirm-req-1",
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["relation"]["case_id"], "case-1")
        self.assertEqual(result["relation"]["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(result["changed_case_ids"], ["case-1"])
        self.assertEqual(result["affected_months"], ["2026-05"])
        self.assertFalse(result["idempotent_replay"])
        self.assertEqual(repository.save_calls[0]["changed_case_ids"], {"case-1"})
        saved_snapshot = repository.save_calls[0]["snapshot"]
        self.assertEqual(saved_snapshot["pair_relations"]["case-1"]["relation_mode"], "manual_confirmed")
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "confirm_relation")
        self.assertEqual(history["before_relations"], [])
        self.assertEqual(history["after_relations"][0]["case_id"], "case-1")
        self.assertEqual(history["affected_row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(history["created_by"], "finance-user")
        self.assertEqual(facade.calls[0]["reason"], "workbench_relation_write_precondition")

    def test_confirm_relation_persists_evidence_and_display_tags_for_owner_modules(self) -> None:
        repository = FakeRelationRepository()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        result = service.confirm_relation(
            case_id="case-no-oa",
            row_ids=["bank-1"],
            row_types=["bank"],
            relation_mode="no_oa_bank_batch",
            actor_id="finance-user",
            month_scope="2026-05",
            evidence={"batch_key": "fee:2026-05", "row_count": 1},
            display_tags=["免OA", "手续费"],
            special_metadata={"source": "no_oa_bank_batch"},
        )

        self.assertEqual(result["relation"]["evidence"]["batch_key"], "fee:2026-05")
        self.assertEqual(result["relation"]["display_tags"], ["免OA", "手续费"])
        saved_relation = repository.save_calls[0]["snapshot"]["pair_relations"]["case-no-oa"]
        self.assertEqual(saved_relation["evidence"]["row_count"], 1)
        self.assertEqual(saved_relation["display_tags"], ["免OA", "手续费"])

    def test_confirm_relation_preserves_explicit_row_alignment_metadata(self) -> None:
        repository = FakeRelationRepository()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )
        row_alignment = {
            "version": 1,
            "source": "manual_selection",
            "links": [
                {
                    "oa_row_id": "oa-88050",
                    "bank_row_ids": ["bank-60000", "bank-28050"],
                    "invoice_row_ids": [],
                    "evidence": ["manual_selection"],
                }
            ],
            "unresolved_row_ids": [],
        }

        result = service.confirm_relation(
            case_id="case-row-alignment",
            row_ids=["oa-88050", "bank-60000", "bank-28050"],
            row_types=["oa", "bank", "bank"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
            special_metadata={"row_alignment": row_alignment},
        )

        self.assertEqual(result["relation"]["special_metadata"]["row_alignment"], row_alignment)
        saved_relation = repository.save_calls[0]["snapshot"]["pair_relations"]["case-row-alignment"]
        self.assertEqual(saved_relation["special_metadata"]["row_alignment"], row_alignment)

    def test_confirm_relation_replays_same_idempotency_key_without_second_save(self) -> None:
        repository = FakeRelationRepository()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        first = service.confirm_relation(
            case_id="case-1",
            row_ids=["oa-1", "bank-1"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
            idempotency_key="confirm-req-1",
        )
        second = service.confirm_relation(
            case_id="case-1",
            row_ids=["oa-1", "bank-1"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
            idempotency_key="confirm-req-1",
        )

        self.assertEqual(first["relation"], second["relation"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(len(repository.save_calls), 1)

    def test_confirm_relation_fails_fast_when_row_is_active_in_another_case(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-existing": {
                        "case_id": "case-existing",
                        "row_ids": ["bank-1", "invoice-1"],
                        "row_types": ["bank", "invoice"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                        "created_by": "finance-user",
                        "created_at": "2026-05-01T10:00:00+00:00",
                        "updated_at": "2026-05-01T10:00:00+00:00",
                    }
                }
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="case-new",
                row_ids=["bank-1", "oa-1"],
                row_types=["bank", "oa"],
                relation_mode="manual_confirmed",
                actor_id="finance-user",
                month_scope="2026-05",
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_active_row_conflict")
        self.assertEqual(repository.save_calls, [])

    def test_confirm_relation_fails_fast_when_freshness_precondition_is_explicit(self) -> None:
        repository = FakeRelationRepository()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(
                {
                    "status": "stale",
                    "rows": [],
                    "groups": [],
                    "read_model_scope_keys": ["2026-05"],
                    "stale_reasons": ["dirty_scope:2026-05"],
                    "refresh_enqueued": True,
                }
            ),
            require_fresh_relations=True,
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="case-1",
                row_ids=["oa-1", "bank-1"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                actor_id="finance-user",
                month_scope="2026-05",
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_read_model_not_fresh")
        self.assertEqual(context.exception.payload["read_model_status"], "stale")
        self.assertEqual(context.exception.payload["read_model_stale_reasons"], ["dirty_scope:2026-05"])
        self.assertEqual(context.exception.payload["read_model_scope_keys"], ["2026-05"])
        self.assertTrue(context.exception.payload["refresh_enqueued"])
        self.assertEqual(repository.save_calls, [])

    def test_cancel_relation_saves_cancelled_case_and_audit_history(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-1": {
                        "case_id": "case-1",
                        "row_ids": ["oa-1", "bank-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                        "created_by": "finance-user",
                        "created_at": "2026-05-01T10:00:00+00:00",
                        "updated_at": "2026-05-01T10:00:00+00:00",
                    }
                }
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        result = service.cancel_relation(
            case_id="case-1",
            actor_id="finance-user",
            reason="undo manual match",
            occurred_at="2026-05-02T11:00:00+00:00",
        )

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["relation"]["status"], "cancelled")
        saved_snapshot = repository.save_calls[0]["snapshot"]
        self.assertEqual(saved_snapshot["pair_relations"]["case-1"]["status"], "cancelled")
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "cancel_relation")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-1")
        self.assertEqual(history["after_relations"], [])
        self.assertEqual(history["created_by"], "finance-user")

    def test_cancel_relations_for_row_ids_saves_changed_cases_and_history(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-etc": {
                        "case_id": "case-etc",
                        "row_ids": ["etc_summary_batch_1", "oa-1"],
                        "row_types": ["etc_summary", "oa"],
                        "status": "active",
                        "relation_mode": "etc_business_batch",
                        "month_scope": "2026-05",
                        "created_by": "finance-user",
                        "created_at": "2026-05-01T10:00:00+00:00",
                        "updated_at": "2026-05-01T10:00:00+00:00",
                    }
                }
            }
        )
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        result = service.cancel_relations_for_row_ids(
            row_ids=["etc_summary_batch_1"],
            actor_id="system",
            reason="ETC业务批次删除",
            history_operation_type="etc_summary_unmerged",
        )

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["changed_case_ids"], ["case-etc"])
        self.assertEqual(result["affected_months"], ["2026-05"])
        self.assertEqual(facade.calls[0]["row_ids"], ["etc_summary_batch_1"])
        self.assertEqual(facade.calls[0]["scope_keys_hint"], ["2026-05"])
        saved_snapshot = repository.save_calls[0]["snapshot"]
        self.assertEqual(saved_snapshot["pair_relations"]["case-etc"]["status"], "cancelled")
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "etc_summary_unmerged")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-etc")
        self.assertEqual(history["affected_row_ids"], ["etc_summary_batch_1", "oa-1"])

    def test_cancel_relations_by_case_ids_loads_and_saves_all_targets_once(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "flow-1": {
                        "case_id": "flow-1",
                        "row_ids": ["bank-1"],
                        "row_types": ["bank"],
                        "status": "active",
                        "relation_mode": "bank_flow_rule_batch",
                        "month_scope": "2026-05",
                    },
                    "flow-2": {
                        "case_id": "flow-2",
                        "row_ids": ["bank-2"],
                        "row_types": ["bank"],
                        "status": "active",
                        "relation_mode": "bank_flow_rule_batch",
                        "month_scope": "2026-06",
                    },
                    "unrelated": {
                        "case_id": "unrelated",
                        "row_ids": ["bank-3"],
                        "row_types": ["bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-06",
                    },
                }
            }
        )
        service = WorkbenchRelationCommandService(relation_repository=repository)

        result = service.cancel_relations_by_case_ids(
            case_ids=["flow-1", "flow-2", "flow-1"],
            actor_id="finance-user",
            reason="重置流水规则批次",
            history_operation_type="bank_flow_rule_batch_reset_submitted_withdraw",
        )

        self.assertEqual(result["changed_case_ids"], ["flow-1", "flow-2"])
        self.assertEqual(result["affected_months"], ["2026-05", "2026-06"])
        self.assertEqual(
            repository.scoped_load_calls,
            [{"row_ids": [], "case_ids": ["flow-1", "flow-2"]}],
        )
        self.assertEqual(len(repository.save_calls), 1)
        saved = repository.save_calls[0]["snapshot"]
        self.assertEqual(saved["pair_relations"]["flow-1"]["status"], "cancelled")
        self.assertEqual(saved["pair_relations"]["flow-2"]["status"], "cancelled")
        self.assertNotIn("unrelated", saved["pair_relations"])
        self.assertEqual(
            saved["pair_relation_history"][0]["operation_type"],
            "bank_flow_rule_batch_reset_submitted_withdraw",
        )

    def test_update_relation_metadata_for_case_id_checks_freshness_and_records_history(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "case-existing-etc": {
                        "case_id": "case-existing-etc",
                        "row_ids": ["oa-1", "bank-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "2026-05",
                        "amount_check": {"status": "matched"},
                        "created_by": "finance-user",
                        "created_at": "2026-05-01T10:00:00+00:00",
                        "updated_at": "2026-05-01T10:00:00+00:00",
                    }
                }
            }
        )
        facade = FakeRelationFacade()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
            require_fresh_relations=True,
        )

        result = service.update_relation_metadata_for_case_id(
            case_id="case-existing-etc",
            actor_id="system_existing_etc_batch_link",
            amount_check={"status": "matched", "invoice_total": "100.00"},
            special_metadata={"etc_batch_link": {"external_etc_batch_id": "ETC-1"}},
            display_tags=["ETC发票已关联"],
            note="关联 ETC 发票",
            history_operation_type="link_existing_etc_batch",
        )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["changed_case_ids"], ["case-existing-etc"])
        self.assertEqual(result["relation"]["amount_check"]["invoice_total"], "100.00")
        self.assertEqual(result["relation"]["special_metadata"]["etc_batch_link"]["external_etc_batch_id"], "ETC-1")
        self.assertEqual(result["relation"]["display_tags"], ["ETC发票已关联"])
        self.assertEqual(facade.calls[0]["row_ids"], ["oa-1", "bank-1"])
        saved_snapshot = repository.save_calls[0]["snapshot"]
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "link_existing_etc_batch")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-existing-etc")
        self.assertEqual(history["after_relations"][0]["amount_check"]["invoice_total"], "100.00")

    def test_update_relation_metadata_for_case_id_can_upgrade_relation_mode(self) -> None:
        repository = FakeRelationRepository(
            {
                "pair_relations": {
                    "turnover:rel-1": {
                        "case_id": "turnover:rel-1",
                        "row_ids": ["oa-1", "bank-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "finance-user",
                        "created_at": "2026-05-01T10:00:00+00:00",
                        "updated_at": "2026-05-01T10:00:00+00:00",
                    }
                }
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        result = service.update_relation_metadata_for_case_id(
            case_id="turnover:rel-1",
            relation_mode="turnover_manual_closure",
            actor_id="system_turnover_rule_sync",
            special_metadata={
                "requires_oa": True,
                "requires_invoice": False,
                "paired_requirement_tag_codes": ["external_turnover"],
            },
            history_operation_type="turnover_rule_tag_requirement_sync",
        )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["relation"]["relation_mode"], "turnover_manual_closure")
        self.assertTrue(result["relation"]["special_metadata"]["requires_oa"])
        self.assertFalse(result["relation"]["special_metadata"]["requires_invoice"])
        saved_snapshot = repository.save_calls[0]["snapshot"]
        saved_relation = saved_snapshot["pair_relations"]["turnover:rel-1"]
        self.assertEqual(saved_relation["relation_mode"], "turnover_manual_closure")
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "turnover_rule_tag_requirement_sync")
        self.assertEqual(history["before_relations"][0]["relation_mode"], "manual_confirmed")
        self.assertEqual(history["after_relations"][0]["relation_mode"], "turnover_manual_closure")

    def test_confirm_relation_allows_oa_invoice_offset_auto_match_mode(self) -> None:
        repository = FakeRelationRepository()
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        result = service.confirm_relation(
            case_id="case-oa-offset",
            row_ids=["oa-offset-1", "oa-att-inv-1"],
            row_types=["oa", "invoice"],
            relation_mode="oa_invoice_offset_auto_match",
            actor_id="system_auto_match",
            month_scope="2026-02",
        )

        self.assertEqual(result["relation"]["relation_mode"], "oa_invoice_offset_auto_match")
        self.assertEqual(repository.save_calls[0]["snapshot"]["pair_relations"]["case-oa-offset"]["created_by"], "system_auto_match")

    def test_replace_existing_confirm_uses_requested_history_operation_type(self) -> None:
        before_relation = {
            "case_id": "case-repair",
            "row_ids": ["oa-1", "bank-1"],
            "row_types": ["oa", "bank"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "created_by": "finance-user",
            "created_at": "2026-05-01T10:00:00+00:00",
            "updated_at": "2026-05-01T10:00:00+00:00",
        }
        repository = FakeRelationRepository({"pair_relations": {"case-repair": before_relation}})
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=FakeRelationFacade(),
        )

        result = service.confirm_relation(
            case_id="case-repair",
            row_ids=["oa-1", "bank-1", "invoice-1"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="system_repair",
            month_scope="2026-05",
            before_relations=[before_relation],
            replace_existing=True,
            history_operation_type="repair_missing_oa_attachment_context",
        )

        self.assertEqual(result["relation"]["row_ids"], ["oa-1", "bank-1", "invoice-1"])
        history = repository.save_calls[0]["snapshot"]["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "repair_missing_oa_attachment_context")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-repair")

    def test_relation_mode_registry_rejects_automatic_decision_as_write_fact(self) -> None:
        self.assertIn("manual_confirmed", VALID_WORKBENCH_RELATION_MODES)
        self.assertIn("etc_batch_invoice_link", VALID_WORKBENCH_RELATION_MODES)
        self.assertIn("bank_flow_rule_batch", VALID_WORKBENCH_RELATION_MODES)
        self.assertNotIn("automatic_decision", VALID_WORKBENCH_RELATION_MODES)
        service = WorkbenchRelationCommandService(
            relation_repository=FakeRelationRepository(),
            relation_facade=FakeRelationFacade(),
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="case-1",
                row_ids=["oa-1", "bank-1"],
                row_types=["oa", "bank"],
                relation_mode="automatic_decision",
                actor_id="finance-user",
                month_scope="2026-05",
            )

        self.assertEqual(context.exception.error_code, "invalid_workbench_relation_mode")


if __name__ == "__main__":
    unittest.main()
