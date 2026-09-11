from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)
from fin_ops_platform.services.workbench_relation_grouping import WorkbenchRelationGroupingService


def command_service() -> WorkbenchRelationCommandService:
    pair_service = WorkbenchPairRelationService()
    return WorkbenchRelationCommandService(
        relation_repository=WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=pair_service,
            save_repository=False,
        )
    )


class WorkbenchRelationCommandServiceTests(unittest.TestCase):
    def test_confirm_and_withdraw_keep_submitted_batch_display_identity(self) -> None:
        service = command_service()
        grouping = WorkbenchRelationGroupingService()
        bank_ids = [f"bank-{index}" for index in range(3)]
        rows = {rid: {"id": rid, "type": "bank", "object_identity_key": rid, "amount": "10.00"} for rid in bank_ids}
        rows.update({kind: {"id": kind, "type": kind, "object_identity_key": kind, "amount": "30.00"} for kind in ("oa", "invoice")})
        batch = {"batch_id": "batch", "status": "submitted", "version": 1,
                 "row_ids": bank_ids, "total_amount": "30.00"}

        def displayed_batch():
            payload = grouping.group_payload("all", rows_by_id=rows,
                active_relations=service.active_relations_for_row_ids(list(rows)))
            groups = [*payload["paired"]["groups"], *payload["unpaired"]["groups"]]
            grouping.apply_bank_batches(groups, [batch])
            return next(group for group in groups if group.get("bank_batches"))

        service.confirm_relation(case_id="batch", row_ids=bank_ids, row_types=["bank"] * 3,
            relation_mode="bank_flow_rule_batch", actor_id="tester")
        before = displayed_batch()["bank_batches"]
        service.confirm_relation(case_id="merged", row_ids=list(rows),
            row_types=[rows[rid]["type"] for rid in rows], relation_mode="manual_confirmed",
            actor_id="tester", replace_existing=True, history_operation_type="confirm_link")
        self.assertEqual(displayed_batch()["bank_batches"][0]["batch_id"], before[0]["batch_id"])
        self.assertEqual(displayed_batch()["bank_batches"][0]["member_ids"], bank_ids)
        preview = service.preview_withdraw_relation(row_ids=list(rows), row_types=[rows[rid]["type"] for rid in rows])
        service.withdraw_relation(case_id="merged", actor_id="tester", row_ids=list(rows),
            row_types=[rows[rid]["type"] for rid in rows], preview_id=preview["preview_id"],
            operation_type=preview["operation_type"], expected_versions=preview["submit_expected_versions"])
        self.assertEqual(displayed_batch()["bank_batches"][0]["member_ids"], bank_ids)
        self.assertEqual(service.get_active_relation_by_case_id("batch")["row_ids"], bank_ids)

    def test_batch_withdraw_unwinds_merges_preserves_other_relations_and_is_idempotent(self) -> None:
        service = command_service()
        bank_ids = [f"batch-bank-{index}" for index in range(5)]
        for case_id, ids, types, mode in [
            ("batch", bank_ids, ["bank"] * 5, "bank_flow_rule_batch"),
            ("oa-invoice", ["oa", "invoice"], ["oa", "invoice"], "manual_confirmed"),
            ("other-batch", ["other-bank-1", "other-bank-2"], ["bank"] * 2, "bank_flow_rule_batch"),
        ]:
            service.confirm_relation(case_id=case_id, row_ids=ids, row_types=types,
                                     relation_mode=mode, actor_id="tester", month_scope="2026-06")
        ids = ["oa", "invoice", *bank_ids]
        types = ["oa", "invoice", *(["bank"] * 5)]
        service.confirm_relation(case_id="merged", row_ids=ids, row_types=types,
                                 relation_mode="manual_confirmed", actor_id="tester", replace_existing=True, history_operation_type="confirm_link")
        service.confirm_relation(case_id="merged-again", row_ids=[*ids, "other-bank-1", "other-bank-2"],
                                 row_types=[*types, "bank", "bank"], relation_mode="manual_confirmed",
                                 actor_id="tester", replace_existing=True, history_operation_type="confirm_link")
        result = service.withdraw_bank_flow_batch(case_id="batch", row_ids=bank_ids, actor_id="tester")
        self.assertEqual(service.active_relations_for_row_ids(bank_ids), [])
        self.assertEqual(service.get_active_relation_by_case_id("oa-invoice")["row_ids"], ["oa", "invoice"])
        self.assertIsNotNone(service.get_active_relation_by_case_id("other-batch"))
        self.assertIn("merged-again", result["changed_case_ids"])
        history = service.list_history()
        repeat = service.withdraw_bank_flow_batch(case_id="batch", row_ids=bank_ids, actor_id="tester")
        self.assertEqual(repeat["changed_case_ids"], [])
        self.assertEqual(history, service.list_history())
        preview = service.preview_withdraw_relation(row_ids=["oa", "invoice"], row_types=["oa", "invoice"])
        self.assertFalse(any(set(bank_ids).intersection(item["row_ids"]) for item in preview["after_relations"]))

    def test_batch_withdraw_without_proven_history_does_not_change_relation(self) -> None:
        service = command_service()
        service.confirm_relation(case_id="unproven", row_ids=["bank", "oa"], row_types=["bank", "oa"],
                                 relation_mode="manual_confirmed", actor_id="tester")
        before = service.get_active_relation_by_case_id("unproven")
        with self.assertRaises(WorkbenchRelationCommandError):
            service.withdraw_bank_flow_batch(case_id="missing-batch", row_ids=["bank"], actor_id="tester")
        self.assertEqual(before, service.get_active_relation_by_case_id("unproven"))

    def test_identical_formal_plan_rerun_is_a_true_noop(self) -> None:
        service = command_service()
        plan = SimpleNamespace(
            case_id="CASE-FORMAL-NOOP",
            row_ids=("oa-formal-noop", "bank-formal-noop"),
            row_types=("oa", "bank"),
            relation_fingerprint="formal-noop-fingerprint",
            batch_hash="formal-noop-batch",
            rule_code="exact_amount",
            rule_version="1",
            amount_minor=10000,
            currency="CNY",
            scope_keys=("2026-05",),
            evidence_summary=(("amount", "100.00"),),
            target_case_id=None,
            oa_attachment_bindings=(),
            relation_mode="manual_confirmed",
        )

        first = service.confirm_formal_relation_plans(
            [plan],
            actor_id="system:workbench-matching",
        )
        before = service.get_active_relation_by_case_id("CASE-FORMAL-NOOP")
        history_before = service.list_history()
        second = service.confirm_formal_relation_plans(
            [plan],
            actor_id="system:workbench-matching",
        )
        after = service.get_active_relation_by_case_id("CASE-FORMAL-NOOP")

        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(second["status"], "noop")
        self.assertEqual(second["changed_case_ids"], [])
        self.assertEqual(second["histories"], [])
        self.assertEqual(after, before)
        self.assertEqual(service.list_history(), history_before)

    def test_identical_formal_extension_rerun_is_a_true_noop(self) -> None:
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="CASE-FORMAL-EXTENSION-NOOP",
            row_ids=["oa-formal-extension", "bank-formal-extension"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="system:workbench-matching",
            month_scope="2026-05",
        )
        service = WorkbenchRelationCommandService(
            relation_repository=WorkbenchRelationCommandRepositoryAdapter(
                pair_relation_service=pair_service,
                save_repository=False,
            )
        )
        plan = SimpleNamespace(
            case_id="CASE-FORMAL-EXTENSION-NOOP",
            row_ids=(
                "oa-formal-extension",
                "bank-formal-extension",
                "invoice-formal-extension",
            ),
            row_types=("oa", "bank", "invoice"),
            relation_fingerprint="formal-extension-noop-fingerprint",
            batch_hash="formal-extension-noop-batch",
            rule_code="exact_amount",
            rule_version="1",
            amount_minor=10000,
            currency="CNY",
            scope_keys=("2026-05",),
            evidence_summary=(("amount", "100.00"),),
            target_case_id="CASE-FORMAL-EXTENSION-NOOP",
            oa_attachment_bindings=(),
            relation_mode="manual_confirmed",
        )

        first = service.confirm_formal_relation_plans(
            [plan],
            actor_id="system:workbench-matching",
        )
        before = service.get_active_relation_by_case_id("CASE-FORMAL-EXTENSION-NOOP")
        history_before = service.list_history()
        second = service.confirm_formal_relation_plans(
            [plan],
            actor_id="system:workbench-matching",
        )
        after = service.get_active_relation_by_case_id("CASE-FORMAL-EXTENSION-NOOP")

        self.assertEqual(first["status"], "confirmed")
        self.assertEqual(second["status"], "noop")
        self.assertEqual(second["changed_case_ids"], [])
        self.assertEqual(second["histories"], [])
        self.assertEqual(after, before)
        self.assertEqual(service.list_history(), history_before)

    def test_confirm_and_query_use_canonical_relation_state(self) -> None:
        service = command_service()
        result = service.confirm_relation(
            case_id="case-direct",
            row_ids=["bank-1", "invoice-1"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="tester",
            month_scope="2026-05",
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertNotIn("read_model_status", result)
        self.assertEqual(
            [relation["case_id"] for relation in service.active_relations_for_row_ids(["bank-1"])],
            ["case-direct"],
        )

    def test_conflicting_active_relation_fails_without_freshness_gate(self) -> None:
        service = command_service()
        service.confirm_relation(
            case_id="case-one",
            row_ids=["bank-1", "invoice-1"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="tester",
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="case-two",
                row_ids=["bank-1", "invoice-2"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                actor_id="tester",
            )

        self.assertEqual(context.exception.error_code, "workbench_relation_active_row_conflict")

    def test_confirm_maps_immutable_attachment_member_drop_to_relation_conflict(self) -> None:
        service = command_service()
        service.confirm_relation(
            case_id="CASE-OA-ATTACHMENT",
            row_ids=["oa-exp-2444", "inv_imported_0956"],
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            actor_id="system:workbench-matching",
            special_metadata={
                "oa_attachment_bindings": [
                    {
                        "parent_oa_row_id": "oa-exp-2444",
                        "invoice_row_ids": ["inv_imported_0956"],
                    }
                ],
                "immutable_oa_attachment_binding": True,
                "contains_immutable_oa_attachment_binding": True,
            },
        )

        with self.assertRaises(WorkbenchRelationCommandError) as context:
            service.confirm_relation(
                case_id="CASE-MANUAL-INVALID",
                row_ids=["oa-exp-2444", "bank-140"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                actor_id="finance",
                replace_existing=True,
            )

        self.assertEqual(
            context.exception.error_code,
            "workbench_relation_immutable_oa_attachment_binding",
        )

    def test_large_relation_confirm_and_withdraw_keep_all_members_and_idempotency(self) -> None:
        service = command_service()
        row_ids = [
            "oa-large-1",
            "bank-large-1",
            *[f"invoice-large-{index}" for index in range(98)],
        ]
        row_types = ["oa", "bank", *(["invoice"] * 98)]
        confirm_kwargs = {
            "case_id": "case-large",
            "row_ids": row_ids,
            "row_types": row_types,
            "relation_mode": "manual_confirmed",
            "actor_id": "tester",
            "month_scope": "2026-05",
            "idempotency_key": "confirm:case-large",
        }

        confirmed = service.confirm_relation(**confirm_kwargs)
        confirm_replay = service.confirm_relation(**confirm_kwargs)
        preview = service.preview_withdraw_relation(
            row_ids=row_ids,
            row_types=row_types,
            month_scope="2026-05",
        )
        withdraw_kwargs = {
            "case_id": "case-large",
            "actor_id": "tester",
            "row_ids": row_ids,
            "row_types": row_types,
            "idempotency_key": "withdraw:case-large",
            "preview_id": preview["preview_id"],
            "operation_type": preview["operation_type"],
            "expected_versions": preview["submit_expected_versions"],
        }
        withdrawn = service.withdraw_relation(**withdraw_kwargs)
        withdraw_replay = service.withdraw_relation(**withdraw_kwargs)

        self.assertEqual(confirmed["relation"]["row_ids"], row_ids)
        self.assertEqual(confirmed["relation"]["row_types"], row_types)
        self.assertEqual(confirm_replay["relation"], confirmed["relation"])
        self.assertTrue(confirm_replay["idempotent_replay"])
        self.assertEqual(preview["before_relations"][0]["row_ids"], row_ids)
        self.assertEqual(withdrawn["affected_row_ids"], row_ids)
        self.assertEqual(withdraw_replay["affected_row_ids"], withdrawn["affected_row_ids"])
        self.assertTrue(withdraw_replay["idempotent_replay"])
        self.assertEqual(service.active_relations_for_row_ids(row_ids), [])

    def test_withdraw_restores_same_case_predecessor_through_command_boundary(self) -> None:
        predecessor = {
            "case_id": "CASE-SAME",
            "row_ids": ["oa-1", "invoice-1"],
            "row_types": ["oa", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "version": 1,
            "special_metadata": {"restorable_on_withdraw": True},
        }
        active = {
            "case_id": "CASE-SAME",
            "row_ids": ["oa-1", "bank-1", "invoice-1"],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-05",
            "version": 3,
        }
        pair_service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {"CASE-SAME": active},
                "pair_relation_history": [
                    {
                        "operation_id": "hist-command-same-case",
                        "operation_type": "confirm_link",
                        "before_relations": [predecessor],
                        "after_relations": [active],
                    }
                ],
            }
        )
        service = WorkbenchRelationCommandService(
            relation_repository=WorkbenchRelationCommandRepositoryAdapter(
                pair_relation_service=pair_service,
                save_repository=False,
            )
        )
        row_ids = list(active["row_ids"])
        row_types = list(active["row_types"])

        preview = service.preview_withdraw_relation(
            row_ids=row_ids,
            row_types=row_types,
            month_scope="2026-05",
        )
        withdraw_kwargs = {
            "case_id": "CASE-SAME",
            "actor_id": "finance",
            "row_ids": row_ids,
            "row_types": row_types,
            "idempotency_key": "withdraw:same-case",
            "preview_id": preview["preview_id"],
            "operation_type": preview["operation_type"],
            "expected_versions": preview["submit_expected_versions"],
        }
        withdrawn = service.withdraw_relation(**withdraw_kwargs)
        replay = service.withdraw_relation(**withdraw_kwargs)

        self.assertTrue(preview["can_submit"])
        self.assertEqual(preview["after_relations"][0]["case_id"], "CASE-SAME")
        self.assertEqual(withdrawn["restored_relations"][0]["version"], 5)
        self.assertIsNone(service.get_active_relation_by_row_id("bank-1"))
        self.assertEqual(
            service.get_active_relation_by_row_id("oa-1")["row_ids"],
            ["oa-1", "invoice-1"],
        )
        self.assertTrue(replay["idempotent_replay"])


if __name__ == "__main__":
    unittest.main()
