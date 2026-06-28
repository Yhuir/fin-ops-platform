from __future__ import annotations

from copy import deepcopy
import unittest

from fin_ops_platform.services.workbench_relation_command_service import (
    VALID_WORKBENCH_RELATION_MODES,
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)


class FakeRelationRepository:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self.snapshot = deepcopy(snapshot or {})
        self.load_calls = 0
        self.save_calls: list[dict[str, object]] = []

    def load_workbench_pair_relations(self) -> dict[str, object]:
        self.load_calls += 1
        return deepcopy(self.snapshot)

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


class FakeRelationFacade:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload or {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "stale_reasons": [],
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
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
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
        self.assertNotIn("read_model_status", preview)
        self.assertNotIn("read_model_scope_keys", preview)
        self.assertNotIn("refresh_enqueued", preview)
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
                "stale_reasons": ["dirty_scope:2026-05"],
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
        self.assertNotIn("read_model_status", result)
        self.assertEqual(facade.calls, [])
        self.assertEqual(repository.save_calls[-1]["changed_case_ids"], {"case-new"})

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
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
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
        self.assertNotIn("read_model_status", result)

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

    def test_confirm_relation_uses_canonical_write_safety_when_distribution_is_stale(self) -> None:
        repository = FakeRelationRepository()
        facade = FakeRelationFacade(
            {
                "status": "stale",
                "rows": [],
                "groups": [],
                "stale_reasons": ["dirty_scope:2026-05"],
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
            relation_facade=facade,
        )

        result = service.confirm_relation(
            case_id="case-1",
            row_ids=["oa-1", "bank-1"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            actor_id="finance-user",
            month_scope="2026-05",
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertNotIn("read_model_status", result)
        self.assertEqual(facade.calls, [])
        self.assertEqual(repository.save_calls[0]["changed_case_ids"], {"case-1"})

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
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
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
        saved_snapshot = repository.save_calls[0]["snapshot"]
        self.assertEqual(saved_snapshot["pair_relations"]["case-etc"]["status"], "cancelled")
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "etc_summary_unmerged")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-etc")
        self.assertEqual(history["affected_row_ids"], ["etc_summary_batch_1", "oa-1"])

    def test_update_relation_metadata_for_case_id_records_history(self) -> None:
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
        service = WorkbenchRelationCommandService(
            relation_repository=repository,
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
        self.assertNotIn("read_model_status", result)
        saved_snapshot = repository.save_calls[0]["snapshot"]
        history = saved_snapshot["pair_relation_history"][0]
        self.assertEqual(history["operation_type"], "link_existing_etc_batch")
        self.assertEqual(history["before_relations"][0]["case_id"], "case-existing-etc")
        self.assertEqual(history["after_relations"][0]["amount_check"]["invoice_total"], "100.00")

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
